from sqlalchemy.orm import Session as DbSession

from app.layers.base import LayerOutput
from app.persistence.models import SessionModel, TurnModel
from app.providers.base import LLMProvider


DEFAULT_SYSTEM_PROMPT = """You are a document analyst for a teaching demo about layered context.
Use a calm, precise tone. Answer from the uploaded documents and visible conversation context.
If the context is insufficient, say what is missing. Do not invent citations.
Keep answers concise unless the user asks for depth."""


class L1SystemLayer:
    name = "L1_system"

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        content = session.system_prompt or DEFAULT_SYSTEM_PROMPT
        return LayerOutput(
            name=self.name,
            role="system",
            content=content,
            token_count=provider.count_tokens(content, model=session.model),
            metadata={"lifecycle": "permanent"},
        )

