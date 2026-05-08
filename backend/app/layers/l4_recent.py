from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.layers.base import LayerOutput
from app.persistence.models import SessionModel, TurnModel
from app.providers.base import LLMProvider


class L4RecentLayer:
    name = "L4_recent"

    def __init__(self, *, include_all: bool = False):
        self.include_all = include_all

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        all_turns = db.scalars(
            select(TurnModel)
            .where(TurnModel.session_id == session.id)
            .order_by(TurnModel.created_at, TurnModel.id)
        ).all()
        if self.include_all:
            selected = all_turns
            about_to_age_out: list[str] = []
        else:
            selected = all_turns[-get_settings().recent_turn_count :]
            about_to_age_out = [t.id for t in selected[:2]] if len(selected) >= 5 else []

        if selected:
            content = "\n\n".join(
                f"{turn_item.role.upper()} [{idx + 1}]\n{turn_item.content}"
                for idx, turn_item in enumerate(selected)
            )
        else:
            content = "No recent turns yet."

        return LayerOutput(
            name=self.name,
            role="user",
            content=content,
            token_count=provider.count_tokens(content, model=session.model),
            metadata={
                "turn_count": len(selected),
                "all_turn_count": len(all_turns),
                "window_size": None if self.include_all else get_settings().recent_turn_count,
                "include_all": self.include_all,
                "about_to_age_out_turn_ids": about_to_age_out,
            },
        )

