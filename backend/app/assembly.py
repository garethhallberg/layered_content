from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.layers.base import LayerOutput
from app.layers.l1_system import L1SystemLayer
from app.layers.l2_documents import L2DocumentsLayer
from app.layers.l3_summary import L3SummaryLayer
from app.layers.l4_recent import L4RecentLayer
from app.layers.l5_working import L5WorkingLayer
from app.persistence.models import SessionModel, TurnModel
from app.providers.base import LLMProvider, Message


@dataclass
class AssemblyResult:
    messages: list[Message]
    trace: dict[str, Any]
    layers: list[LayerOutput]


def assemble_layers(
    db: DbSession,
    session: SessionModel,
    turn: TurnModel,
    provider: LLMProvider,
    *,
    mode: str,
    summariser_event: dict[str, Any] | None = None,
) -> AssemblyResult:
    if mode == "naive":
        layer_builders = [
            L1SystemLayer(),
            L2DocumentsLayer(),
            L4RecentLayer(include_all=True),
        ]
    else:
        layer_builders = [
            L1SystemLayer(),
            L2DocumentsLayer(),
            L3SummaryLayer(),
            L4RecentLayer(),
            L5WorkingLayer(),
        ]

    outputs: list[LayerOutput] = []
    for builder in layer_builders:
        outputs.append(builder.build(db, session, turn, provider, outputs))

    messages: list[Message] = [
        {"role": output.role, "content": output.content} for output in outputs
    ]
    total_tokens = sum(output.token_count for output in outputs)
    trace = {
        "mode": mode,
        "provider": session.provider,
        "model": session.model,
        "layers": [output.to_trace() for output in outputs],
        "total_tokens": total_tokens,
        "latency_ms": 0,
        "cost_estimate_usd": None,
        "summariser_event": summariser_event,
    }
    return AssemblyResult(messages=messages, trace=trace, layers=outputs)

