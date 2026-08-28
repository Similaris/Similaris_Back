from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxBuilder

from app.core.config import settings
from app.models.analysis import Batch
from app.services.analysis.segment_service import SegmentService
from app.services.documents.exceptions import (
    EmptyUploadError,
    FileTooLargeError,
    UnsupportedDocumentTypeError,
)
from app.services.documents.upload_service import UploadFilePayload, UploadService


def build_docx(*paragraphs: str) -> bytes:
    document = DocxBuilder()
    for text in paragraphs:
        document.add_paragraph(text)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


class FakeBatchRepository:
    def __init__(self):
        self.created_batches = []

    def create_for_user(self, user_id):
        batch = Batch(id=len(self.created_batches) + 1, user_id=user_id)
        self.created_batches.append(batch)
        return batch


class FakeDocumentRepository:
    def __init__(self):
        self.documents = []

    def create(self, document):
        document.id = len(self.documents) + 1
        self.documents.append(document)
        return document

    def save(self, document):
        return document


class FakeSegmentRepository:
    def __init__(self):
        self.segments_by_document = {}

    def replace_for_document(self, document_id, segments):
        self.segments_by_document[document_id] = list(segments)
        return list(segments)


def build_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    batch_repository = FakeBatchRepository()
    document_repository = FakeDocumentRepository()
    segment_service = SegmentService(db=None, repository=FakeSegmentRepository())
    service = UploadService(
        db=None,
        batch_repository=batch_repository,
        document_repository=document_repository,
        segment_service=segment_service,
    )
    return service, batch_repository, document_repository


def test_upload_documents_creates_batch_document_and_segments(
    monkeypatch, tmp_path
):
    service, _, document_repository = build_service(monkeypatch, tmp_path)
    content = build_docx("The student wrote an original academic paper.")

    result = service.upload_documents(
        user_id=10,
        files=[UploadFilePayload(filename="Paper Final.DOCX", content=content)],
    )

    assert result.batch.user_id == 10
    assert len(result.documents) == 1

    uploaded = result.documents[0]
    assert uploaded.document is document_repository.documents[0]
    assert uploaded.document.filename == "Paper Final.DOCX"
    assert uploaded.document.file_type == "docx"
    assert uploaded.document.status == "pendente"
    assert uploaded.document.content_hash is not None
    assert uploaded.document.extraction_ms is not None
    assert uploaded.segment_count > 0
    assert Path(uploaded.document.file_path).read_bytes() == content


def test_upload_documents_rejects_empty_file_list(monkeypatch, tmp_path):
    service, batch_repository, _ = build_service(monkeypatch, tmp_path)

    with pytest.raises(EmptyUploadError, match="Nenhum arquivo"):
        service.upload_documents(user_id=1, files=[])

    assert batch_repository.created_batches == []


def test_upload_documents_rejects_unsupported_extension_before_persisting(
    monkeypatch, tmp_path
):
    service, batch_repository, document_repository = build_service(
        monkeypatch, tmp_path
    )

    with pytest.raises(UnsupportedDocumentTypeError, match="não suportado"):
        service.upload_documents(
            user_id=1,
            files=[UploadFilePayload(filename="notas.txt", content=b"texto")],
        )

    assert batch_repository.created_batches == []
    assert document_repository.documents == []


def test_upload_documents_rejects_file_above_size_limit(monkeypatch, tmp_path):
    service, batch_repository, _ = build_service(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "upload_max_file_size_mb", 1)

    oversized_content = b"x" * (1024 * 1024 + 1)

    with pytest.raises(FileTooLargeError, match="excede o limite"):
        service.upload_documents(
            user_id=1,
            files=[UploadFilePayload(filename="grande.pdf", content=oversized_content)],
        )

    assert batch_repository.created_batches == []


def test_upload_documents_marks_extraction_failure_and_continues(
    monkeypatch, tmp_path
):
    service, _, document_repository = build_service(monkeypatch, tmp_path)
    valid_content = build_docx("Valid document with real text content.")

    result = service.upload_documents(
        user_id=3,
        files=[
            UploadFilePayload(filename="corrompido.docx", content=b"nao e docx"),
            UploadFilePayload(filename="valido.docx", content=valid_content),
        ],
    )

    failed, succeeded = result.documents
    assert failed.document.status == "erro"
    assert failed.document.error_message
    assert failed.segment_count == 0

    assert succeeded.document.status == "pendente"
    assert succeeded.segment_count > 0
    assert len(document_repository.documents) == 2
