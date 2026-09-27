from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from app.models.analysis import Batch, Document
from app.repositories.analysis import (
    AnalysisResultRepository,
    BatchRepository,
    DocumentRepository,
)
from app.services.documents.document_extractor import extract_document_text
from app.services.documents.exceptions import (
    DocumentExtractionError,
    RetryableDocumentProcessingError,
)
from app.core.config import settings

if TYPE_CHECKING:
    from app.services.analysis.hybrid_analysis import HybridAnalysisService
    from app.services.analysis.segment_service import SegmentService

TERMINAL_DOCUMENT_STATUSES = {"concluido", "erro"}


class DocumentProcessingService:
    """Executa no worker o pipeline completo de um documento."""

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
        batch_repository: BatchRepository | None = None,
        segment_service: SegmentService | None = None,
        analysis_result_repository: AnalysisResultRepository | None = None,
        hybrid_analysis_factory: Callable[[], HybridAnalysisService] | None = None,
    ):
        self.db = db
        self.document_repository = document_repository or DocumentRepository(db)
        self.batch_repository = batch_repository or BatchRepository(db)
        self.analysis_result_repository = (
            analysis_result_repository or AnalysisResultRepository(db)
        )
        if segment_service is None:
            from app.services.analysis.segment_service import SegmentService

            segment_service = SegmentService(db)
        self.segment_service = segment_service
        if hybrid_analysis_factory is None:
            from app.services.analysis.hybrid_analysis import HybridAnalysisService

            hybrid_analysis_factory = lambda: HybridAnalysisService(db)
        self.hybrid_analysis_factory = hybrid_analysis_factory

    def process_document(self, document_id: int) -> None:
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            return

        if document.status in TERMINAL_DOCUMENT_STATUSES:
            # Reentregas tambem reparam uma finalizacao de lote interrompida.
            self._finalize_batch_if_done(document.batch)
            return
        if document.status not in {"pendente", "processando"}:
            return

        self._mark_processing(document)

        try:
            content = Path(document.file_path).read_bytes()
        except FileNotFoundError:
            self._finish_with_error(
                document, "Arquivo não encontrado no armazenamento."
            )
            return
        except OSError as error:
            raise RetryableDocumentProcessingError(
                f"Falha temporaria ao acessar o documento {document_id}: {error}"
            ) from error

        try:
            started = time.perf_counter()
            extracted_text = extract_document_text(content, document.filename)
            document.extraction_ms = int((time.perf_counter() - started) * 1000)
        except DocumentExtractionError as error:
            self._finish_with_error(document, str(error))
            return

        try:
            self.segment_service.persist_document_segments(document, extracted_text)

            analysis = self.hybrid_analysis_factory().analyze_document(document)
            self.analysis_result_repository.replace_for_document(
                document.id, analysis
            )
            document.lexical_ms = analysis.lexical_ms
            document.semantic_ms = analysis.semantic_ms
            document.plagiarism_percent = Decimal(
                str(round(analysis.overall_score * 100, 2))
            )
            document.analysis_profile = {
                "version": 1,
                "semantic_model": settings.semantic_model_name,
                "segment_max_words": settings.segment_max_words,
                "lexical_cosine_threshold": settings.lexical_cosine_threshold,
                "lexical_jaccard_threshold": settings.lexical_jaccard_threshold,
                "semantic_threshold": settings.reference_search_semantic_threshold,
                "reference_search_top_n": settings.reference_search_top_n,
                "tfidf_weight": settings.hybrid_tfidf_weight,
                "jaccard_weight": settings.hybrid_jaccard_weight,
                "lexical_weight": settings.hybrid_lexical_weight,
                "semantic_weight": settings.hybrid_semantic_weight,
                "moderate_threshold": settings.hybrid_classification_moderate_threshold,
                "high_threshold": settings.hybrid_classification_high_threshold,
                "very_high_threshold": settings.hybrid_classification_very_high_threshold,
                "suspicious_final_threshold": settings.hybrid_suspicious_final_threshold,
                "suspicious_semantic_threshold": settings.hybrid_suspicious_semantic_threshold,
                "suspicious_tfidf_threshold": settings.hybrid_suspicious_tfidf_threshold,
                "suspicious_jaccard_threshold": settings.hybrid_suspicious_jaccard_threshold,
                "top_n": settings.hybrid_top_n,
            }
            document.reference_fingerprint = analysis.reference_fingerprint
            document.status = "concluido"
        except Exception as error:
            self.db.rollback()
            raise RetryableDocumentProcessingError(
                f"Falha temporaria no processamento do documento {document_id}: {error}"
            ) from error

        try:
            document.error_message = None
            document.finished_at = datetime.now(UTC)
            self.document_repository.save(document)
            self._finalize_batch_if_done(document.batch)
        except Exception as error:
            self.db.rollback()
            raise RetryableDocumentProcessingError(
                f"Falha temporaria ao finalizar o documento {document_id}: {error}"
            ) from error

    def mark_failed_after_retries(self, document_id: int, message: str) -> None:
        self.db.rollback()
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            return
        if document.status in TERMINAL_DOCUMENT_STATUSES:
            self._finalize_batch_if_done(document.batch)
            return
        self._finish_with_error(document, message)

    def _mark_processing(self, document: Document) -> None:
        now = datetime.now(UTC)
        document.status = "processando"
        document.started_at = document.started_at or now
        document.finished_at = None
        document.error_message = None
        if document.batch.status == "pendente":
            document.batch.status = "processando"
        self.document_repository.save(document)

    def _finish_with_error(self, document: Document, message: str) -> None:
        self.analysis_result_repository.delete_by_document(document.id)
        document.status = "erro"
        document.error_message = message
        document.finished_at = datetime.now(UTC)
        self.document_repository.save(document)
        self._finalize_batch_if_done(document.batch)

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
