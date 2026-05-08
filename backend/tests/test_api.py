from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.main import app
from app.persistence.database import Base, get_db
from app.persistence.models import SessionModel, TurnModel
from app.providers.base import ProviderError, rough_count


class FailingProvider:
    name = "failing"

    def complete(self, messages, *, model: str, max_tokens: int):
        raise ProviderError("test provider failed")

    def count_tokens(self, text: str, *, model: str) -> int:
        return rough_count(text)


def test_message_provider_failure_does_not_orphan_user_turn(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.rollback()
            db.close()

    monkeypatch.setattr("app.main.get_provider", lambda name: FailingProvider())
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post("/sessions", json={"provider": "openai"}).json()
            response = client.post(
                f"/sessions/{created['id']}/messages",
                json={"content": "This should not persist"},
            )

        assert response.status_code == 502
        with SessionLocal() as db:
            session = db.scalar(select(SessionModel).where(SessionModel.id == created["id"]))
            turns = db.scalars(select(TurnModel).where(TurnModel.session_id == created["id"])).all()
            assert session is not None
            assert turns == []
    finally:
        app.dependency_overrides.clear()


def test_message_length_limit_returns_413():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.rollback()
            db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post("/sessions", json={"provider": "openai"}).json()
            response = client.post(
                f"/sessions/{created['id']}/messages",
                json={"content": "x" * 13000},
            )

        assert response.status_code == 413
    finally:
        app.dependency_overrides.clear()
