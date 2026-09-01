from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.analysis import Batch, Document
from app.repositories.analysis import BatchRepository, DocumentRepository
from app.services.documents.document_extractor import extract_document_text
from app.services.documents.exceptions import DocumentExtractionError

if TYPE_CHECKING:
    from app.services.analysis.segment_service import SegmentService

TERMINAL_DOCUMENT_STATUSES = {"concluido", "erro"}


class DocumentProcessingService:
    """Executa o pipeline de análise de um documento do lote.

    Chamado pelos workers Celery: lê o arquivo do disco, extrai o texto,
    segmenta e atualiza os status do documento e do lote. Erros nunca
    propagam para fora — o documento é marcado com ``erro`` e o restante
    do lote segue normalmente.
    """

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
        batch_repository: BatchRepository | None = None,
        segment_service: SegmentService | None = None,
    ):
        self.document_repository = document_repository or DocumentRepository(db)
        self.batch_repository = batch_repository or BatchRepository(db)
        if segment_service is None:
            # Import tardio para evitar ciclo com app.services.analysis
            from app.services.analysis.segment_service import SegmentService

            segment_service = SegmentService(db)
        self.segment_service = segment_service

    def process_document(self, document_id: int) -> None:
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            return

        # Idempotência: mensagens reentregues pelo broker não reprocessam
        # documentos que já saíram do estado pendente.
        if document.status != "pendente":
            return

        self._mark_processing(document)

        try:
            content = Path(document.file_path).read_bytes()
            started = time.perf_counter()
            extracted_text = extract_document_text(content, document.filename)
            document.extraction_ms = int((time.perf_counter() - started) * 1000)
            self.segment_service.persist_document_segments(document, extracted_text)
            document.status = "concluido"
        except DocumentExtractionError as error:
            document.status = "erro"
            document.error_message = str(error)
        except FileNotFoundError:
            document.status = "erro"
            document.error_message = "Arquivo não encontrado no armazenamento."
        except Exception as error:  # noqa: BLE001 - nunca travar o lote
            document.status = "erro"
            document.error_message = f"Falha inesperada no processamento: {error}"

        document.finished_at = datetime.now(UTC)
        self.document_repository.save(document)
        self._finalize_batch_if_done(document.batch)

    def _mark_processing(self, document: Document) -> None:
        now = datetime.now(UTC)
        document.status = "processando"
        document.started_at = now
        if document.batch.status == "pendente":
            document.batch.status = "processando"
        self.document_repository.save(document)

    def _finalize_batch_if_done(self, batch: Batch) -> None:
        documents = self.document_repository.list_by_batch(batch.id)
        if any(
            document.status not in TERMINAL_DOCUMENT_STATUSES
            for document in documents
        ):
            return

        has_success = any(
            document.status == "concluido" for document in documents
        )
        batch.status = "concluido" if has_success else "erro"
        batch.finished_at = datetime.now(UTC)
        self.batch_repository.save(batch)
