from app.api.auth import get_current_user
from app.core.config import settings
from app.main import app


def test_upload_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user)

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("doc.docx", b"conteudo", "application/octet-stream"))],
    )

    assert response.status_code == 403


def test_upload_creates_pending_batch_and_dispatches_processing(client, build_docx):
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
    assert "segment_count" not in document
    assert client.dispatched == [document["id"]]

    segments_response = client.get(f"/api/documents/{document['id']}/segments")
    assert segments_response.status_code == 200
    assert segments_response.json() == []


def test_upload_then_worker_processing_generates_segments(
    client, build_docx, run_pending_workers
):
    content = build_docx("The student wrote an original academic paper.")

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("paper.docx", content, "application/octet-stream"))],
    )
    document = response.json()["documents"][0]

    run_pending_workers()

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert [item["id"] for item in listed] == [document["id"]]
    assert listed[0]["status"] == "concluido"

    segments_response = client.get(f"/api/documents/{document['id']}/segments")
    assert segments_response.status_code == 200
    segments = segments_response.json()
    assert len(segments) > 0
    assert segments[0]["text_original"]
    assert segments[0]["text_clean"]


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("notas.txt", b"texto simples", "text/plain"))],
    )

    assert response.status_code == 415
    assert "não suportado" in response.json()["detail"]
    assert client.dispatched == []


def test_upload_rejects_file_above_size_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_size_mb", 1)
    oversized_content = b"x" * (1024 * 1024 + 1)

    response = client.post(
        "/api/documents/upload",
        files=[("files", ("grande.pdf", oversized_content, "application/pdf"))],
    )

    assert response.status_code == 413
    assert "excede o limite" in response.json()["detail"]
    assert client.dispatched == []


def test_list_segments_of_unknown_document_returns_404(client):
    response = client.get("/api/documents/999/segments")

    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]
