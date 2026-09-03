from app.api.auth import get_current_user
from app.main import app
from app.models.analysis import Batch


def upload_batch(client, build_docx, filenames: list[str]) -> dict:
    files = [
        (
            "files",
            (name, build_docx(f"Original academic content for {name}."),
             "application/octet-stream"),
        )
        for name in filenames
    ]
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201
    return response.json()


def test_list_batches_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user)

    response = client.get("/api/batches")

    assert response.status_code == 403


def test_list_batches_shows_pending_summary(client, build_docx):
    upload_batch(client, build_docx, ["a.docx", "b.docx"])

    response = client.get("/api/batches")

    assert response.status_code == 200
    batches = response.json()
    assert len(batches) == 1

    batch = batches[0]
    assert batch["status"] == "pendente"
    assert batch["total_documents"] == 2
    assert batch["processed_documents"] == 0
    assert batch["document_counts"] == {
        "pendente": 2,
        "processando": 0,
        "concluido": 0,
        "erro": 0,
    }
    assert batch["finished_at"] is None


def test_list_batches_orders_most_recent_first(client, build_docx):
    first = upload_batch(client, build_docx, ["a.docx"])
    second = upload_batch(client, build_docx, ["b.docx"])

    response = client.get("/api/batches")

    ids = [batch["id"] for batch in response.json()]
    assert ids == [second["batch_id"], first["batch_id"]]


def test_batch_detail_after_processing(client, build_docx, run_pending_workers):
    uploaded = upload_batch(client, build_docx, ["a.docx", "b.docx"])
    batch_id = uploaded["batch_id"]

    run_pending_workers()

    response = client.get(f"/api/batches/{batch_id}")

    assert response.status_code == 200
    batch = response.json()
    assert batch["status"] == "concluido"
    assert batch["finished_at"] is not None
    assert batch["total_documents"] == 2
    assert batch["processed_documents"] == 2
    assert batch["document_counts"]["concluido"] == 2

    for document in batch["documents"]:
        assert document["status"] == "concluido"
        assert document["started_at"] is not None
        assert document["finished_at"] is not None
        assert document["extraction_ms"] is not None


def test_batch_detail_of_unknown_batch_returns_404(client):
    response = client.get("/api/batches/999")

    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]


def test_batch_of_another_user_returns_404(client):
    session = client.session_factory()
    try:
        other_batch = Batch(user_id=None)
        session.add(other_batch)
        session.commit()
        session.refresh(other_batch)
        batch_id = other_batch.id
    finally:
        session.close()

    response = client.get(f"/api/batches/{batch_id}")

    assert response.status_code == 404
