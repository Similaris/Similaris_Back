from io import BytesIO

import pytest
from docx import Document as DocxBuilder
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.auth import User
from app.services.documents import upload_service
from app.services.documents.document_processing import DocumentProcessingService


@pytest.fixture()
def build_docx():
    """Gera um DOCX em memória com os parágrafos informados."""

    def _build(*paragraphs: str) -> bytes:
        document = DocxBuilder()
        for text in paragraphs:
            document.add_paragraph(text)

        stream = BytesIO()
        document.save(stream)
        return stream.getvalue()

    return _build


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    user = User(name="Rafael", email="rafael@example.com", password_hash="hash")
    session.add(user)
    session.commit()
    session.refresh(user)

    # O upload publica tarefas Celery; nos testes registramos os IDs para
    # simular os workers depois, sem depender de um broker real.
    dispatched: list[int] = []
    monkeypatch.setattr(
        upload_service, "dispatch_document_processing", dispatched.append
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as test_client:
        test_client.dispatched = dispatched
        test_client.session_factory = TestingSessionLocal
        yield test_client

    app.dependency_overrides.clear()
    session.close()


@pytest.fixture()
def run_pending_workers(client):
    """Simula os workers Celery processando as tarefas enfileiradas."""

    def _run() -> None:
        while client.dispatched:
            document_id = client.dispatched.pop(0)
            db = client.session_factory()
            try:
                DocumentProcessingService(db).process_document(document_id)
            finally:
                db.close()

    return _run
