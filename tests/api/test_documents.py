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


def build_docx(*paragraphs: str) -> bytes:
    document = DocxBuilder()
    for text in paragraphs:
        document.add_paragraph(text)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


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

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    session.close()


def test_upload_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user)

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("doc.docx", b"conteudo", "application/octet-stream"))],
    )

    assert response.status_code == 403


def test_upload_creates_batch_documents_and_segments(client):
    content = build_docx("The student wrote an original academic paper.")

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("paper.docx", content, "application/octet-stream"))],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["batch_id"] == 1
    assert body["status"] == "pendente"

    document = body["documents"][0]
    assert document["filename"] == "paper.docx"
    assert document["file_type"] == "docx"
    assert document["status"] == "pendente"
    assert document["segment_count"] > 0

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [document["id"]]

    segments_response = client.get(f"/api/documents/{document['id']}/segments")
    assert segments_response.status_code == 200
    segments = segments_response.json()
    assert len(segments) == document["segment_count"]
    assert segments[0]["text_original"]
    assert segments[0]["text_clean"]


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("notas.txt", b"texto simples", "text/plain"))],
    )

    assert response.status_code == 415
    assert "não suportado" in response.json()["detail"]


def test_upload_rejects_file_above_size_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_size_mb", 1)
    oversized_content = b"x" * (1024 * 1024 + 1)

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("grande.pdf", oversized_content, "application/pdf"))],
    )

    assert response.status_code == 413
    assert "excede o limite" in response.json()["detail"]


def test_list_segments_of_unknown_document_returns_404(client):
    response = client.get("/api/documents/999/segments")

    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]
