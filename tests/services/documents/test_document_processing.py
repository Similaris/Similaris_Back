from io import BytesIO

import pytest
from docx import Document as DocxBuilder
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.analysis import Batch, Document, Segment
from app.services.documents.document_processing import DocumentProcessingService
from app.services.documents.file_storage import store_document_file


def build_docx(*paragraphs: str) -> bytes:
    document = DocxBuilder()
    for text in paragraphs:
        document.add_paragraph(text)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def create_pending_document(
    db, filename: str = "paper.docx", content: bytes | None = None
) -> Document:
    batch = db.query(Batch).first()
    if batch is None:
        batch = Batch(status="pendente")
        db.add(batch)
        db.commit()
        db.refresh(batch)

    if content is None:
        content = build_docx("The student wrote an original academic paper.")

    file_path = store_document_file(content, filename, batch.id)
    document = Document(
        batch_id=batch.id,
        filename=filename,
        file_type="docx",
        file_path=file_path,
        status="pendente",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_process_document_completes_and_persists_segments(session_factory):
    db = session_factory()
    document = create_pending_document(db)

    DocumentProcessingService(db).process_document(document.id)

    db.refresh(document)
    assert document.status == "concluido"
    assert document.error_message is None
    assert document.extraction_ms is not None
    assert document.started_at is not None
    assert document.finished_at is not None

    segments = db.query(Segment).filter_by(document_id=document.id).all()
    assert len(segments) > 0
    assert segments[0].text_clean

    batch = db.get(Batch, document.batch_id)
    assert batch.status == "concluido"
    assert batch.finished_at is not None
    db.close()


def test_process_document_marks_error_when_extraction_fails(session_factory):
    db = session_factory()
    document = create_pending_document(
        db, filename="corrompido.docx", content=b"nao e um docx"
    )

    DocumentProcessingService(db).process_document(document.id)

    db.refresh(document)
    assert document.status == "erro"
    assert document.error_message
    assert document.finished_at is not None
    assert db.query(Segment).filter_by(document_id=document.id).count() == 0

    # Lote com todos os documentos falhados termina em erro.
    batch = db.get(Batch, document.batch_id)
    assert batch.status == "erro"
    db.close()


def test_process_document_marks_error_when_file_is_missing(session_factory):
    db = session_factory()
    document = create_pending_document(db)
    document.file_path = "caminho/inexistente.docx"
    db.commit()

    DocumentProcessingService(db).process_document(document.id)

    db.refresh(document)
    assert document.status == "erro"
    assert "não encontrado" in document.error_message
    db.close()


def test_process_document_ignores_documents_not_pending(session_factory):
    db = session_factory()
    document = create_pending_document(db)
    document.status = "concluido"
    db.commit()

    DocumentProcessingService(db).process_document(document.id)

    db.refresh(document)
    # Nada muda: mensagens reentregues não reprocessam o documento.
    assert document.started_at is None
    assert db.query(Segment).filter_by(document_id=document.id).count() == 0
    db.close()


def test_process_document_ignores_unknown_document(session_factory):
    db = session_factory()

    DocumentProcessingService(db).process_document(999)

    assert db.query(Document).count() == 0
    db.close()


def test_batch_finishes_only_after_last_document(session_factory):
    db = session_factory()
    first = create_pending_document(db, filename="a.docx")
    second = create_pending_document(db, filename="b.docx")
    service = DocumentProcessingService(db)

    service.process_document(first.id)
    batch = db.get(Batch, first.batch_id)
    assert batch.status == "processando"
    assert batch.finished_at is None

    service.process_document(second.id)
    db.refresh(batch)
    assert batch.status == "concluido"
    assert batch.finished_at is not None
    db.close()


def test_batch_with_partial_failure_still_completes(session_factory):
    db = session_factory()
    failed = create_pending_document(
        db, filename="corrompido.docx", content=b"invalido"
    )
    succeeded = create_pending_document(db, filename="valido.docx")
    service = DocumentProcessingService(db)

    service.process_document(failed.id)
    service.process_document(succeeded.id)

    db.refresh(failed)
    db.refresh(succeeded)
    assert failed.status == "erro"
    assert succeeded.status == "concluido"

    batch = db.get(Batch, failed.batch_id)
    assert batch.status == "concluido"
    db.close()
