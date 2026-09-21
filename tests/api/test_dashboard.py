from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import event

from app.api.auth import get_current_user
from app.main import app
from app.models.analysis import AnalysisResult, Batch, Document, Segment
from app.models.auth import User
from app.models.references import ReferenceDocument, ReferenceSegment


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=timezone.utc)


def _add_batch(db, user_id: int, status: str, created_at: datetime) -> Batch:
    batch = Batch(user_id=user_id, status=status, created_at=created_at)
    db.add(batch)
    db.flush()
    return batch


def _add_document(
    db,
    batch: Batch,
    number: int,
    classification: str | None = None,
) -> Document:
    document = Document(
        batch_id=batch.id,
        filename=f"document-{number}.pdf",
        file_type="pdf",
        file_path=f"uploads/document-{number}.pdf",
        status="concluido",
        created_at=batch.created_at,
    )
    db.add(document)
    db.flush()

    if classification is not None:
        segment = Segment(
            document_id=document.id,
            position=0,
            text_original="Texto suspeito.",
        )
        reference_document = ReferenceDocument(
            title=f"Reference {number}",
            source="test",
            language="en",
            corpus_id=f"reference-{number}",
        )
        db.add_all([segment, reference_document])
        db.flush()
        reference_segment = ReferenceSegment(
            reference_doc_id=reference_document.id,
            position=0,
            text_original="Reference text.",
        )
        db.add(reference_segment)
        db.flush()
        db.add(
            AnalysisResult(
                document_id=document.id,
                segment_id=segment.id,
                reference_segment_id=reference_segment.id,
                final_score=Decimal("0.7500"),
                plagiarism_type=classification,
                is_suspicious=True,
            )
        )

    return document


def test_dashboard_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user)

    response = client.get("/api/dashboard")

    assert response.status_code == 403


def test_dashboard_is_documented_in_openapi(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/dashboard"]["get"]
    assert operation["tags"] == ["dashboard"]
    assert operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/DashboardOut"}


def test_dashboard_for_user_without_analyses(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json() == {
        "summary": {
            "total_batches": 0,
            "total_documents": 0,
            "completed_batches": 0,
            "processing_batches": 0,
        },
        "status_distribution": {
            "pendente": 0,
            "processando": 0,
            "concluido": 0,
            "erro": 0,
        },
        "similarity_distribution": {
            "low": 0,
            "moderate": 0,
            "high": 0,
            "very_high": 0,
        },
        "analyses_over_time": [],
        "recent_analyses": [],
    }


def test_dashboard_aggregates_and_limits_recent_analyses(client):
    db = client.session_factory()
    try:
        user = db.query(User).filter_by(email="rafael@example.com").one()
        batches = [
            _add_batch(db, user.id, "pendente", _utc(2026, 1, 10)),
            _add_batch(db, user.id, "processando", _utc(2026, 2, 10)),
            _add_batch(db, user.id, "erro", _utc(2026, 3, 1)),
            _add_batch(db, user.id, "concluido", _utc(2026, 3, 2)),
            _add_batch(db, user.id, "concluido", _utc(2026, 3, 3)),
            _add_batch(db, user.id, "pendente", _utc(2026, 3, 4)),
        ]
        _add_document(db, batches[0], 1, "LOW")
        _add_document(db, batches[1], 2, "MODERATE")
        _add_document(db, batches[1], 3, "HIGH")
        _add_document(db, batches[3], 4, "VERY_HIGH")
        _add_document(db, batches[4], 5, "LOW")
        db.commit()
        expected_recent_ids = [batch.id for batch in reversed(batches[1:])]
    finally:
        db.close()

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_batches": 6,
        "total_documents": 5,
        "completed_batches": 2,
        "processing_batches": 1,
    }
    assert body["status_distribution"] == {
        "pendente": 2,
        "processando": 1,
        "concluido": 2,
        "erro": 1,
    }
    assert body["similarity_distribution"] == {
        "low": 2,
        "moderate": 1,
        "high": 1,
        "very_high": 1,
    }
    assert body["analyses_over_time"] == [
        {"period": "2026-01", "count": 1},
        {"period": "2026-02", "count": 1},
        {"period": "2026-03", "count": 4},
    ]
    assert len(body["recent_analyses"]) == 5
    assert [item["id"] for item in body["recent_analyses"]] == expected_recent_ids
    assert body["recent_analyses"][0]["document_count"] == 0
    assert body["recent_analyses"][2]["document_count"] == 1


def test_dashboard_isolates_users(client):
    db = client.session_factory()
    try:
        first_user = db.query(User).filter_by(email="rafael@example.com").one()
        second_user = User(
            name="Outro",
            email="outro@example.com",
            password_hash="hash",
        )
        db.add(second_user)
        db.flush()

        first_batch = _add_batch(
            db, first_user.id, "concluido", _utc(2026, 4, 1)
        )
        second_batch = _add_batch(
            db, second_user.id, "processando", _utc(2026, 5, 1)
        )
        _add_document(db, first_batch, 10, "HIGH")
        _add_document(db, second_batch, 11, "VERY_HIGH")
        db.commit()
        second_user_id = second_user.id
        second_batch_id = second_batch.id
    finally:
        db.close()

    app.dependency_overrides[get_current_user] = lambda: User(
        id=second_user_id,
        name="Outro",
        email="outro@example.com",
        password_hash="hash",
    )
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_batches": 1,
        "total_documents": 1,
        "completed_batches": 0,
        "processing_batches": 1,
    }
    assert body["similarity_distribution"]["very_high"] == 1
    assert body["similarity_distribution"]["high"] == 0
    assert [item["id"] for item in body["recent_analyses"]] == [second_batch_id]


def test_dashboard_uses_five_aggregate_queries(client):
    engine = client.session_factory.kw["bind"]
    statements: list[str] = []

    def count_statement(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        response = client.get("/api/dashboard")
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert response.status_code == 200
    assert len(statements) == 5
