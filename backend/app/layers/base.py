from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session as DbSession

from app.persistence.models import SessionModel, TurnModel
from app.providers.base import LLMProvider


@dataclass
class LayerOutput:
    name: str
    role: Literal["system", "user", "assistant"]
    content: str
    token_count: int
    metadata: dict[str, Any]

    def to_trace(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "content": self.content,
            "tokens": self.token_count,
            "metadata": self.metadata,
        }


class Layer(Protocol):
    name: str

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        ...

