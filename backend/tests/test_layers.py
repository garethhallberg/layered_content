from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assembly import assemble_layers
from app.config import resolve_model
from app.persistence.database import Base
from app.persistence.models import DocumentModel, SessionModel, TurnModel
from app.providers.base import Completion, Message, rough_count
from app.summariser import pending_evicted_pairs, run_summariser_if_due


class DummyProvider:
    name = "dummy"

    def complete(self, messages: list[Message], *, model: str, max_tokens: int) -> Completion:
        text = "\n".join(message["content"] for message in messages)
        if "Return only JSON" in text:
            content = (
                '{"intent":"test intent","sub_questions":["first"],'
                '"relevant_doc_sections":["doc intro"]}'
            )
        elif "Compress the following exchange" in text:
            content = "The old exchange was compressed into a durable rolling summary."
        else:
            content = "answer"
        return Completion(content, rough_count(text), rough_count(content), 12)

    def count_tokens(self, text: str, *, model: str) -> int:
        return rough_count(text)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_session(db) -> SessionModel:
    session = SessionModel(
        mode="layered",
        provider="openai",
        model="test-model",
        system_prompt="System constraints.",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def add_turn(db, session_id: str, role: str, content: str, offset: int) -> TurnModel:
    turn = TurnModel(
        session_id=session_id,
        role=role,
        content=content,
        token_count=rough_count(content),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset),
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn


def add_pair(db, session_id: str, pair_index: int) -> tuple[TurnModel, TurnModel]:
    return (
        add_turn(db, session_id, "user", f"user {pair_index}", pair_index * 2),
        add_turn(db, session_id, "assistant", f"assistant {pair_index}", pair_index * 2 + 1),
    )


def test_layer_assembly_order_and_token_total(db):
    session = make_session(db)
    db.add(
        DocumentModel(
            session_id=session.id,
            name="sample.txt",
            content="A useful document.",
            token_count=3,
        )
    )
    db.commit()
    turn = add_turn(db, session.id, "user", "What is useful?", 1)

    result = assemble_layers(db, session, turn, DummyProvider(), mode="layered")

    assert [layer["name"] for layer in result.trace["layers"]] == [
        "L1_system",
        "L2_documents",
        "L3_summary",
        "L4_recent",
        "L5_working",
    ]
    assert result.trace["total_tokens"] == sum(
        layer["tokens"] for layer in result.trace["layers"]
    )


def test_sliding_window_eviction_keeps_last_six_turns(db):
    session = make_session(db)
    for index in range(4):
        add_pair(db, session.id, index)
    current = add_turn(db, session.id, "user", "current", 99)

    result = assemble_layers(db, session, current, DummyProvider(), mode="layered")
    l4 = next(layer for layer in result.trace["layers"] if layer["name"] == "L4_recent")

    assert l4["metadata"]["turn_count"] == 6
    assert "user 0" not in l4["content"]
    assert "assistant 0" not in l4["content"]
    assert "current" in l4["content"]


def test_summariser_triggers_when_four_evicted_pairs_are_pending(db):
    session = make_session(db)
    for index in range(7):
        add_pair(db, session.id, index)
    add_turn(db, session.id, "user", "new question", 99)

    assert len(pending_evicted_pairs(db, session.id)) >= 4
    event = run_summariser_if_due(db, session, DummyProvider())

    assert event is not None
    assert event["pairs_summarised"] >= 4
    assert len(session.summaries) == 1
    assert "rolling summary" in session.summaries[0].content

    second_event = run_summariser_if_due(db, session, DummyProvider())
    assert second_event is None


def test_provider_model_mismatch_resolves_to_provider_default():
    assert resolve_model("mistral", "gpt-4o-mini") == "mistral-small-2603"
    assert resolve_model("anthropic", "gpt-5-mini") == "claude-sonnet-4-20250514"
    assert resolve_model("openai", "claude-sonnet-4-20250514") == "gpt-5-mini"
    assert resolve_model("mistral", "mistral-medium-3-5") == "mistral-medium-3-5"
