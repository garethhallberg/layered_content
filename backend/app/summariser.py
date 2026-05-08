import json
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.persistence.models import SessionModel, SummaryModel, TurnModel
from app.providers.base import LLMProvider


def covered_turn_ids(db: DbSession, session_id: str) -> set[str]:
    summaries = db.scalars(
        select(SummaryModel).where(SummaryModel.session_id == session_id)
    ).all()
    covered: set[str] = set()
    for summary in summaries:
        covered.update(json.loads(summary.covers_turn_ids or "[]"))
    return covered


def pending_evicted_pairs(db: DbSession, session_id: str) -> list[tuple[TurnModel, TurnModel]]:
    settings = get_settings()
    turns = db.scalars(
        select(TurnModel)
        .where(TurnModel.session_id == session_id)
        .order_by(TurnModel.created_at, TurnModel.id)
    ).all()
    recent_ids = {turn.id for turn in turns[-settings.recent_turn_count :]}
    covered = covered_turn_ids(db, session_id)
    eligible = [turn for turn in turns if turn.id not in recent_ids and turn.id not in covered]
    pairs: list[tuple[TurnModel, TurnModel]] = []
    i = 0
    while i + 1 < len(eligible):
        first, second = eligible[i], eligible[i + 1]
        if first.role == "user" and second.role == "assistant":
            pairs.append((first, second))
            i += 2
        else:
            i += 1
    return pairs


def run_summariser_if_due(
    db: DbSession, session: SessionModel, provider: LLMProvider
) -> dict[str, Any] | None:
    settings = get_settings()
    pairs = pending_evicted_pairs(db, session.id)
    if len(pairs) < settings.summary_threshold_pairs:
        return None
    pairs = pairs[: settings.summary_batch_pairs]

    exchange = "\n\n".join(
        f"USER:\n{user.content}\n\nASSISTANT:\n{assistant.content}"
        for user, assistant in pairs
    )
    prompt = (
        "Compress the following exchange into 2-4 sentences capturing decisions made, "
        "facts established, and open threads. Preserve specifics that might be referenced later.\n\n"
        f"{exchange}"
    )
    started = perf_counter()
    completion = provider.complete(
        [{"role": "user", "content": prompt}],
        model=session.model,
        max_tokens=350,
    )
    latency_ms = completion.latency_ms or int((perf_counter() - started) * 1000)
    covers = [turn.id for pair in pairs for turn in pair]
    summary = SummaryModel(
        session_id=session.id,
        content=completion.content,
        covers_turn_ids=json.dumps(covers),
    )
    db.add(summary)
    db.flush()
    return {
        "summary_id": summary.id,
        "pairs_summarised": len(pairs),
        "covers_turn_ids": covers,
        "latency_ms": latency_ms,
        "prompt_tokens": completion.prompt_tokens,
        "completion_tokens": completion.completion_tokens,
    }
