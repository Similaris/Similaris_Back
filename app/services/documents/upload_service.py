from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import Batch, Document
from app.repositories.analysis import BatchRepository, DocumentRepository
from app.services.documents.document_extractor import extract_document_text
from app.services.documents.exceptions import (
    DocumentExtractionError,
    EmptyUploadError,
    FileTooLargeError,
    UnsupportedDocumentTypeError,
)
from app.services.documents.file_storage import (
    compute_content_hash,
    store_document_file,
)

if TYPE_CHECKING:
    from app.services.analysis.segment_service import SegmentService

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}


@dataclass(frozen=True, slots=True)
class UploadFilePayload:
    """Arquivo recebido no upload, independente do framework HTTP."""

    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class UploadedDocument:
    """Documento criado no upload com a contagem de segmentos gerados."""

    document: Document
    segment_count: int


@dataclass(frozen=True, slots=True)
class UploadResult:
    batch: Batch
    documents: list[UploadedDocument]


class UploadService:
    """Orquestra o fluxo de upload: validação, armazenamento e segmentação."""

    def __init__(
        self,
        db: Session,
        batch_repository: BatchRepository | None = None,
        document_repository: DocumentRepository | None = None,
        segment_service: SegmentService | None = None,
    ):
        self.batch_repository = batch_repository or BatchRepository(db)
        self.document_repository = document_repository or DocumentRepository(db)
        if segment_service is None:
            # Import tardio para evitar ciclo com app.services.analysis
            from app.services.analysis.segment_service import SegmentService

            segment_service = SegmentService(db)
        self.segment_service = segment_service

    def upload_documents(
        self, user_id: int, files: list[UploadFilePayload]
    ) -> UploadResult:
        """Valida os arquivos, cria o lote e processa cada documento.

        A validação é feita antes de qualquer persistência: se algum
        arquivo for inválido, nada é criado. Falhas de extração não
        interrompem o lote — o documento é marcado com status ``erro``
        e os demais seguem o fluxo normalmente.
        """
        self._validate_files(files)

        batch = self.batch_repository.create_for_user(user_id)
        documents: list[UploadedDocument] = []

        for payload in files:
            documents.append(self._process_file(batch, payload))

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

    def _process_file(
        self, batch: Batch, payload: UploadFilePayload
    ) -> UploadedDocument:
        file_path = store_document_file(payload.content, payload.filename, batch.id)
        document = self.document_repository.create(
            Document(
                batch_id=batch.id,
                filename=payload.filename,
                file_type=Path(payload.filename).suffix.lower().lstrip("."),
                file_path=file_path,
                content_hash=compute_content_hash(payload.content),
                status="pendente",
            )
        )

        started = time.perf_counter()
        try:
            extracted_text = extract_document_text(payload.content, payload.filename)
        except DocumentExtractionError as error:
            document.status = "erro"
            document.error_message = str(error)
            self.document_repository.save(document)
            return UploadedDocument(document=document, segment_count=0)

        document.extraction_ms = int((time.perf_counter() - started) * 1000)
        segments = self.segment_service.persist_document_segments(
            document, extracted_text
        )
        self.document_repository.save(document)
        return UploadedDocument(document=document, segment_count=len(segments))
