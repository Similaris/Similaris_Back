from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxBuilder

from app.core.config import settings
from app.models.analysis import Batch
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


def build_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    batch_repository = FakeBatchRepository()
    document_repository = FakeDocumentRepository()
    dispatched: list[int] = []
    service = UploadService(
        db=None,
        batch_repository=batch_repository,
        document_repository=document_repository,
        dispatch_document=dispatched.append,
    )
    return service, batch_repository, document_repository, dispatched


def test_upload_documents_stores_files_and_dispatches_processing(
    monkeypatch, tmp_path
):
    service, _, document_repository, dispatched = build_service(
        monkeypatch, tmp_path
    )
    content = build_docx("The student wrote an original academic paper.")

    result = service.upload_documents(
        user_id=10,
        files=[UploadFilePayload(filename="Paper Final.DOCX", content=content)],
    )

    assert result.batch.user_id == 10
    assert len(result.documents) == 1

    document = result.documents[0]
    assert document is document_repository.documents[0]
    assert document.filename == "Paper Final.DOCX"
    assert document.file_type == "docx"
    assert document.status == "pendente"
    assert document.content_hash is not None
    assert document.extraction_ms is None
    assert Path(document.file_path).read_bytes() == content
    assert dispatched == [document.id]


def test_upload_documents_dispatches_after_creating_all_documents(
    monkeypatch, tmp_path
):
    service, _, document_repository, dispatched = build_service(
        monkeypatch, tmp_path
    )
    content = build_docx("Any valid text.")

    created_before_dispatch: list[int] = []

    def record_dispatch(document_id: int) -> None:
        created_before_dispatch.append(len(document_repository.documents))
        dispatched.append(document_id)

    service.dispatch_document = record_dispatch

    result = service.upload_documents(
        user_id=1,
        files=[
            UploadFilePayload(filename="a.docx", content=content),
            UploadFilePayload(filename="b.docx", content=content),
        ],
    )

    assert dispatched == [document.id for document in result.documents]
    # Todos os documentos do lote já existiam quando a primeira tarefa saiu.
    assert created_before_dispatch == [2, 2]


def test_upload_documents_rejects_empty_file_list(monkeypatch, tmp_path):
    service, batch_repository, _, dispatched = build_service(monkeypatch, tmp_path)

    with pytest.raises(EmptyUploadError, match="Nenhum arquivo"):
        service.upload_documents(user_id=1, files=[])

    assert batch_repository.created_batches == []
    assert dispatched == []


def test_upload_documents_rejects_unsupported_extension_before_persisting(
    monkeypatch, tmp_path
):
    service, batch_repository, document_repository, dispatched = build_service(
        monkeypatch, tmp_path
    )

    with pytest.raises(UnsupportedDocumentTypeError, match="não suportado"):
        service.upload_documents(
            user_id=1,
            files=[UploadFilePayload(filename="notas.txt", content=b"texto")],
        )

    assert batch_repository.created_batches == []
    assert document_repository.documents == []
    assert dispatched == []


def test_upload_documents_rejects_file_above_size_limit(monkeypatch, tmp_path):
    service, batch_repository, _, dispatched = build_service(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "upload_max_file_size_mb", 1)

    oversized_content = b"x" * (1024 * 1024 + 1)

    with pytest.raises(FileTooLargeError, match="excede o limite"):
        service.upload_documents(
            user_id=1,
            files=[UploadFilePayload(filename="grande.pdf", content=oversized_content)],
        )

    assert batch_repository.created_batches == []
    assert dispatched == []
