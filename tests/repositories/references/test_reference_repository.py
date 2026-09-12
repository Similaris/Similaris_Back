import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.models.references import ReferenceDocument, ReferenceSegment
from app.repositories.references import ReferenceRepository


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def reference(corpus_id="source-document00001.txt", **kwargs):
    return ReferenceDocument(
        title="A source", source="pan-pc-11", corpus_id=corpus_id, **kwargs
    )


def segment(position=1):
    return ReferenceSegment(
        position=position,
        start_offset=2,
        end_offset=14,
        text_original="Source text.",
        text_clean="source text",
    )


def test_reference_has_stable_identity_and_original_offsets(db):
    repository = ReferenceRepository(db)
    with db.begin():
        document = repository.add(
            reference(content_sha256="a" * 64, import_signature="b" * 64),
            [segment()],
        )
        document_id = document.id
        segment_id = document.segments[0].id

    found = repository.get_by_corpus_id("pan-pc-11", "source-document00001.txt")
    assert found.id == document_id
    assert found.language == "en"
    assert found.content_sha256 == "a" * 64
    assert found.segments[0].id == segment_id
    assert found.segments[0].start_offset == 2
    assert found.segments[0].end_offset == 14


def test_duplicate_corpus_identity_is_rejected_by_database(db):
    repository = ReferenceRepository(db)
    with db.begin():
        repository.add(reference(), [segment()])

    with pytest.raises(IntegrityError):
        with db.begin():
            repository.add(reference(), [segment()])

    assert len(list(repository.iter_segments())) == 1


def test_index_rows_are_ordered_and_only_include_english_pan_references(db):
    repository = ReferenceRepository(db)
    with db.begin():
        repository.add(reference("source-document00002.txt"), [segment(2), segment(1)])
        repository.add(reference("source-document00001.txt"), [segment()])
        repository.add(reference("source-document00003.txt", language="de"), [segment()])
        repository.add(reference(None), [segment()])

    rows = list(repository.iter_segments())
    assert [
        (row.reference_document.corpus_id, row.position) for row in rows
    ] == [
        ("source-document00001.txt", 1),
        ("source-document00002.txt", 1),
        ("source-document00002.txt", 2),
    ]


def test_reference_and_segments_rollback_together(db):
    repository = ReferenceRepository(db)
    with pytest.raises(ValueError, match="interrupted"):
        with db.begin():
            repository.add(reference(), [segment()])
            raise ValueError("interrupted")

    assert repository.get_by_corpus_id("pan-pc-11", "source-document00001.txt") is None
    assert list(repository.iter_segments()) == []


def test_get_segments_by_ids_returns_only_prepared_scope_with_documents(db):
    repository = ReferenceRepository(db)
    with db.begin():
        first = repository.add(reference("source-document00002.txt"), [segment(2)])
        second = repository.add(reference("source-document00001.txt"), [segment()])
        german = repository.add(
            reference("source-document00003.txt", language="de"), [segment()]
        )
        ids = [first.segments[0].id, second.segments[0].id, german.segments[0].id]

    rows = repository.get_segments_by_ids([*reversed(ids), ids[0], 999])

    assert {row.id for row in rows} == set(ids[:2])
    assert len(rows) == 2
    assert {row.reference_document.corpus_id for row in rows} == {
        "source-document00001.txt", "source-document00002.txt",
    }


def test_get_segments_by_ids_batches_queries_without_lazy_document_loads(db):
    repository = ReferenceRepository(db)
    with db.begin():
        document = repository.add(reference(), [segment(), segment(2)])
        ids = [row.id for row in document.segments]
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        rows = repository.get_segments_by_ids([*ids, *range(1000, 1598)])
        titles = [row.reference_document.title for row in rows]
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)

    assert len(statements) == 3
    assert titles == ["A source", "A source"]


def test_get_segments_by_ids_refreshes_existing_session_objects(db):
    repository = ReferenceRepository(db)
    with db.begin():
        document = repository.add(reference(), [segment()])
        segment_id = document.segments[0].id
    row = repository.get_segments_by_ids([segment_id])[0]
    db.execute(
        update(ReferenceSegment)
        .where(ReferenceSegment.id == segment_id)
        .values(text_clean="changed text")
        .execution_options(synchronize_session=False)
    )
    assert row.text_clean == "source text"

    assert repository.get_segments_by_ids([segment_id])[0].text_clean == "changed text"


def test_get_segments_by_ids_empty_selection_does_not_query(db, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("An empty selection must not query the database.")

    monkeypatch.setattr(db, "scalars", fail)
    assert ReferenceRepository(db).get_segments_by_ids([]) == []
