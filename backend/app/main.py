import json
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.assembly import assemble_layers
from app.config import get_settings, resolve_model
from app.document_parser import parse_upload
from app.layers.l1_system import DEFAULT_SYSTEM_PROMPT
from app.persistence.database import get_db, init_db
from app.persistence.models import (
    DocumentModel,
    SessionModel,
    TraceModel,
    TurnModel,
)
from app.providers.factory import get_provider
from app.providers.base import ProviderError
from app.summariser import run_summariser_if_due


class CreateSessionRequest(BaseModel):
    mode: str | None = None
    provider: str | None = None
    model: str | None = None


class PatchSessionRequest(BaseModel):
    mode: str | None = None
    provider: str | None = None
    model: str | None = None


class MessageRequest(BaseModel):
    content: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Layered Context Document Analyst", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
def create_session(
    payload: CreateSessionRequest | None = None,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    payload = payload or CreateSessionRequest()
    mode = payload.mode or "layered"
    if mode not in {"layered", "naive"}:
        raise HTTPException(status_code=400, detail="mode must be layered or naive")
    provider_name = payload.provider or settings.llm_provider
    get_provider(provider_name)
    session = SessionModel(
        mode=mode,
        provider=provider_name,
        model=resolve_model(provider_name, payload.model or settings.llm_model),
        system_prompt=DEFAULT_SYSTEM_PROMPT,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return serialize_session(db, session)


@app.get("/sessions/{session_id}")
def get_session(session_id: str, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    session = must_get_session(db, session_id)
    normalize_session_model(db, session)
    return serialize_session(db, session)


@app.patch("/sessions/{session_id}")
def patch_session(
    session_id: str,
    payload: PatchSessionRequest,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    session = must_get_session(db, session_id)
    if payload.mode is not None:
        if payload.mode not in {"layered", "naive"}:
            raise HTTPException(status_code=400, detail="mode must be layered or naive")
        session.mode = payload.mode
    if payload.provider is not None:
        get_provider(payload.provider)
        session.provider = payload.provider
    if payload.model is not None:
        session.model = resolve_model(session.provider, payload.model)
    else:
        session.model = resolve_model(session.provider, session.model)
    db.commit()
    db.refresh(session)
    return serialize_session(db, session)


@app.post("/sessions/{session_id}/documents")
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    session = must_get_session(db, session_id)
    content = await parse_upload(file)
    provider = get_provider(session.provider)
    document = DocumentModel(
        session_id=session.id,
        name=file.filename or "document",
        content=content,
        token_count=provider.count_tokens(content, model=session.model),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return serialize_document(document)


@app.delete("/sessions/{session_id}/documents/{document_id}")
def delete_document(
    session_id: str,
    document_id: str,
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    must_get_session(db, session_id)
    document = db.get(DocumentModel, document_id)
    if document is None or document.session_id != session_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(document)
    db.commit()
    return {"status": "deleted"}


@app.post("/sessions/{session_id}/messages")
def send_message(
    session_id: str,
    payload: MessageRequest,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    session = must_get_session(db, session_id)
    normalize_session_model(db, session)
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    if len(payload.content) > settings.max_message_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Message is too large. Maximum length is {settings.max_message_chars} characters.",
        )
    provider = get_provider(session.provider)
    user_turn = TurnModel(
        session_id=session.id,
        role="user",
        content=payload.content,
        token_count=provider.count_tokens(payload.content, model=session.model),
    )
    db.add(user_turn)
    db.flush()

    try:
        summariser_event = None
        if session.mode == "layered":
            summariser_event = run_summariser_if_due(db, session, provider)

        assembly = assemble_layers(
            db,
            session,
            user_turn,
            provider,
            mode=session.mode,
            summariser_event=summariser_event,
        )
        started = perf_counter()
        completion = provider.complete(
            assembly.messages,
            model=session.model,
            max_tokens=settings.max_tokens,
        )
    except ProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    latency_ms = completion.latency_ms or int((perf_counter() - started) * 1000)
    assistant_turn = TurnModel(
        session_id=session.id,
        role="assistant",
        content=completion.content,
        token_count=provider.count_tokens(completion.content, model=session.model),
    )
    db.add(assistant_turn)
    db.flush()

    trace_payload = assembly.trace
    trace_payload["latency_ms"] = latency_ms
    trace = TraceModel(
        session_id=session.id,
        turn_id=user_turn.id,
        mode=session.mode,
        layers_json=json.dumps(trace_payload),
        total_tokens=trace_payload["total_tokens"],
        latency_ms=latency_ms,
        cost_estimate_usd=None,
    )
    db.add(trace)
    db.commit()
    db.refresh(assistant_turn)

    return {
        "turn_id": user_turn.id,
        "assistant_message": completion.content,
        "trace": trace_payload,
        "user_turn": serialize_turn(user_turn),
        "assistant_turn": serialize_turn(assistant_turn),
    }


@app.get("/sessions/{session_id}/traces")
def get_traces(session_id: str, db: DbSession = Depends(get_db)) -> list[dict[str, Any]]:
    must_get_session(db, session_id)
    traces = db.scalars(
        select(TraceModel)
        .where(TraceModel.session_id == session_id)
        .order_by(TraceModel.created_at)
    ).all()
    return [serialize_trace(trace) for trace in traces]


@app.get("/sessions/{session_id}/traces/{turn_id}")
def get_trace(session_id: str, turn_id: str, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    must_get_session(db, session_id)
    trace = db.scalar(
        select(TraceModel).where(
            TraceModel.session_id == session_id,
            TraceModel.turn_id == turn_id,
        )
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return serialize_trace(trace)


def must_get_session(db: DbSession, session_id: str) -> SessionModel:
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def normalize_session_model(db: DbSession, session: SessionModel) -> None:
    resolved = resolve_model(session.provider, session.model)
    if resolved != session.model:
        session.model = resolved
        db.commit()
        db.refresh(session)


def serialize_session(db: DbSession, session: SessionModel) -> dict[str, Any]:
    documents = db.scalars(
        select(DocumentModel)
        .where(DocumentModel.session_id == session.id)
        .order_by(DocumentModel.uploaded_at)
    ).all()
    turns = db.scalars(
        select(TurnModel)
        .where(TurnModel.session_id == session.id)
        .order_by(TurnModel.created_at)
    ).all()
    traces = db.scalars(
        select(TraceModel)
        .where(TraceModel.session_id == session.id)
        .order_by(TraceModel.created_at)
    ).all()
    return {
        "id": session.id,
        "created_at": session.created_at.isoformat(),
        "mode": session.mode,
        "provider": session.provider,
        "model": session.model,
        "documents": [serialize_document(doc) for doc in documents],
        "turns": [serialize_turn(turn) for turn in turns],
        "traces": [serialize_trace(trace) for trace in traces],
    }


def serialize_document(document: DocumentModel) -> dict[str, Any]:
    return {
        "id": document.id,
        "session_id": document.session_id,
        "name": document.name,
        "token_count": document.token_count,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


def serialize_turn(turn: TurnModel) -> dict[str, Any]:
    return {
        "id": turn.id,
        "session_id": turn.session_id,
        "role": turn.role,
        "content": turn.content,
        "token_count": turn.token_count,
        "created_at": turn.created_at.isoformat(),
    }


def serialize_trace(trace: TraceModel) -> dict[str, Any]:
    payload = json.loads(trace.layers_json)
    payload.update(
        {
            "id": trace.id,
            "session_id": trace.session_id,
            "turn_id": trace.turn_id,
            "mode": trace.mode,
            "created_at": trace.created_at.isoformat(),
        }
    )
    return payload
