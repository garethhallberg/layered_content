import json

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.layers.base import LayerOutput
from app.persistence.models import SessionModel, SummaryModel, TurnModel
from app.providers.base import LLMProvider


class L3SummaryLayer:
    name = "L3_summary"

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        summaries = db.scalars(
            select(SummaryModel)
            .where(SummaryModel.session_id == session.id)
            .order_by(SummaryModel.created_at)
        ).all()
        covers: list[str] = []
        if summaries:
            content = "\n\n".join(summary.content for summary in summaries)
            for summary in summaries:
                covers.extend(json.loads(summary.covers_turn_ids or "[]"))
        else:
            content = "No rolling summary yet."
        return LayerOutput(
            name=self.name,
            role="system",
            content=content,
            token_count=provider.count_tokens(content, model=session.model),
            metadata={"covers_turn_ids": covers, "summary_count": len(summaries)},
        )

