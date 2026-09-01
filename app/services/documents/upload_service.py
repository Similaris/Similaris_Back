from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import Batch, Document
from app.repositories.analysis import BatchRepository, DocumentRepository
from app.services.documents.exceptions import (
    EmptyUploadError,
    FileTooLargeError,
    UnsupportedDocumentTypeError,
)
from app.services.documents.file_storage import (
    compute_content_hash,
    store_document_file,
)

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}


def dispatch_document_processing(document_id: int) -> None:
    """Enfileira o processamento do documento nos workers Celery."""
    # Import tardio para evitar ciclo: a task importa serviços deste pacote.
    from app.tasks.document_tasks import process_document

    process_document.delay(document_id)


@dataclass(frozen=True, slots=True)
class UploadFilePayload:
    """Arquivo recebido no upload, independente do framework HTTP."""

    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class UploadResult:
    batch: Batch
    documents: list[Document]


class UploadService:
    """Orquestra o upload: validação, armazenamento e enfileiramento.

    O processamento pesado (extração e segmentação) acontece de forma
    assíncrona nos workers Celery — o upload apenas registra o lote e os
    documentos com status ``pendente`` e publica uma tarefa por documento.
    """

    def __init__(
        self,
        db: Session,
        batch_repository: BatchRepository | None = None,
        document_repository: DocumentRepository | None = None,
        dispatch_document: Callable[[int], None] | None = None,
    ):
        self.batch_repository = batch_repository or BatchRepository(db)
        self.document_repository = document_repository or DocumentRepository(db)
        self.dispatch_document = dispatch_document or dispatch_document_processing

    def upload_documents(
        self, user_id: int, files: list[UploadFilePayload]
    ) -> UploadResult:
        """Valida os arquivos, cria o lote e enfileira o processamento.

        A validação é feita antes de qualquer persistência: se algum
        arquivo for inválido, nada é criado. As tarefas só são publicadas
        depois que todos os documentos do lote existem no banco, para que
        a finalização do lote nos workers enxergue o conjunto completo.
        """
        self._validate_files(files)

        batch = self.batch_repository.create_for_user(user_id)
        documents = [self._store_file(batch, payload) for payload in files]

        for document in documents:
            self.dispatch_document(document.id)

        return UploadResult(batch=batch, documents=documents)

    def _validate_files(self, files: list[UploadFilePayload]) -> None:
        if not files:
            raise EmptyUploadError("Nenhum arquivo foi enviado.")

        max_size_bytes = settings.upload_max_file_size_mb * 1024 * 1024
        for payload in files:
            extension = Path(payload.filename).suffix.lower()
            if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
                displayed_extension = extension or "sem extensão"
                raise UnsupportedDocumentTypeError(
                    f"Formato de documento não suportado: {displayed_extension}. "
                    "Use PDF ou DOCX."
                )

            if len(payload.content) > max_size_bytes:
                raise FileTooLargeError(
                    f"O arquivo {payload.filename} excede o limite de "
                    f"{settings.upload_max_file_size_mb} MB."
                )

    def _store_file(self, batch: Batch, payload: UploadFilePayload) -> Document:
        file_path = store_document_file(payload.content, payload.filename, batch.id)
        return self.document_repository.create(
            Document(
                batch_id=batch.id,
                filename=payload.filename,
                file_type=Path(payload.filename).suffix.lower().lstrip("."),
                file_path=file_path,
                content_hash=compute_content_hash(payload.content),
                status="pendente",
            )
        )
