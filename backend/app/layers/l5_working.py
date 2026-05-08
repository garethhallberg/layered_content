import json
import re
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings, resolve_model
from app.layers.base import LayerOutput
from app.persistence.models import DocumentModel, SessionModel, TurnModel
from app.providers.base import LLMProvider, Message


class L5WorkingLayer:
    name = "L5_working"

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        prior_layers = prior_layers or []
        model = resolve_model(session.provider, get_settings().planner_model or session.model)
        context = "\n\n".join(f"{layer.name}:\n{layer.content}" for layer in prior_layers)
        prompt = (
            "Return only JSON with this shape: "
            '{"intent": str, "sub_questions": [str], "relevant_doc_sections": [str]}.\n'
            "Read the current question and layers L1-L4, then plan the answer.\n\n"
            f"Current user question:\n{turn.content}\n\nLayers:\n{context}"
        )
        started = perf_counter()
        completion = provider.complete(
            [{"role": "user", "content": prompt}],
            model=model,
            max_tokens=300,
        )
        planner_call_ms = completion.latency_ms or int((perf_counter() - started) * 1000)
        planner = self._parse_planner(completion.content)
        entities = self._extract_entities(turn.content)
        noticed = self._noticed_document_items(db, session.id)
        content = self._render(turn.content, planner, entities, noticed)
        return LayerOutput(
            name=self.name,
            role="system",
            content=content,
            token_count=provider.count_tokens(content, model=session.model),
            metadata={
                "planner": planner,
                "planner_call_ms": planner_call_ms,
                "planner_model": model,
                "extracted_entities": entities,
                "noticed_items": noticed,
            },
        )

    def _parse_planner(self, content: str) -> dict[str, Any]:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            parsed = json.loads(content[start:end])
        except Exception:
            parsed = {}
        return {
            "intent": str(parsed.get("intent") or "Answer the current question."),
            "sub_questions": list(parsed.get("sub_questions") or []),
            "relevant_doc_sections": list(parsed.get("relevant_doc_sections") or []),
        }

    def _extract_entities(self, text: str) -> list[str]:
        entities = re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", text)
        stopwords = {
            "A",
            "An",
            "And",
            "Are",
            "Can",
            "Do",
            "Does",
            "For",
            "How",
            "If",
            "Is",
            "It",
            "Please",
            "Tell",
            "The",
            "What",
            "When",
            "Where",
            "Which",
            "Who",
            "Why",
        }
        cleaned = [
            entity.strip()
            for entity in entities
            if entity.strip() not in stopwords and len(entity.strip()) > 1
        ]
        return list(dict.fromkeys(cleaned))[:8]

    def _noticed_document_items(self, db: DbSession, session_id: str) -> list[str]:
        docs = db.scalars(
            select(DocumentModel)
            .where(DocumentModel.session_id == session_id)
            .order_by(DocumentModel.uploaded_at)
        ).all()
        items: list[str] = []
        for doc in docs[:3]:
            first_line = next(
                (
                    line.strip()
                    for line in doc.content.splitlines()
                    if len(line.strip()) >= 20
                ),
                "",
            )
            if first_line:
                items.append(f"{doc.name}: {first_line[:180]}")
        return items

    def _render(
        self,
        question: str,
        planner: dict[str, Any],
        entities: list[str],
        noticed: list[str],
    ) -> str:
        sub_questions = planner["sub_questions"] or ["No explicit sub-questions identified."]
        sections = planner["relevant_doc_sections"] or ["No specific document sections identified."]
        noticed_items = noticed or ["No document observations available yet."]
        return "\n".join(
            [
                "Working state for this turn:",
                f"Current question: {question}",
                f"Intent: {planner['intent']}",
                f"Extracted entities: {', '.join(entities) if entities else 'None'}",
                "Sub-questions:",
                *[f"- {item}" for item in sub_questions],
                "Relevant document sections:",
                *[f"- {item}" for item in sections],
                "Things noticed but not yet asked about:",
                *[f"- {item}" for item in noticed_items],
            ]
        )
