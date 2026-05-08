from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.layers.base import LayerOutput
from app.persistence.models import DocumentModel, SessionModel, TurnModel
from app.providers.base import LLMProvider


class L2DocumentsLayer:
    name = "L2_documents"

    def build(
        self,
        db: DbSession,
        session: SessionModel,
        turn: TurnModel,
        provider: LLMProvider,
        prior_layers: list[LayerOutput] | None = None,
    ) -> LayerOutput:
        docs = db.scalars(
            select(DocumentModel)
            .where(DocumentModel.session_id == session.id)
            .order_by(DocumentModel.uploaded_at)
        ).all()
        if not docs:
            content = "No documents are currently loaded."
        else:
            content = "\n\n".join(
                f"Document: {doc.name}\n---\n{doc.content}" for doc in docs
            )
        return LayerOutput(
            name=self.name,
            role="system",
            content=content,
            token_count=provider.count_tokens(content, model=session.model),
            metadata={"doc_count": len(docs), "document_names": [doc.name for doc in docs]},
        )

