from __future__ import annotations

from collections import Counter
from datetime import datetime

from pydantic import BaseModel

from app.models.analysis import Batch
from app.schemas.analysis.document import DocumentOut


class BatchDocumentCounts(BaseModel):
    pendente: int = 0
    processando: int = 0
    concluido: int = 0
    erro: int = 0


class BatchSummaryOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    total_documents: int
    processed_documents: int
    document_counts: BatchDocumentCounts

    @classmethod
    def from_batch(cls, batch: Batch) -> BatchSummaryOut:
        return cls(**_summary_fields(batch))


class BatchDetailOut(BatchSummaryOut):
    documents: list[DocumentOut]

    @classmethod
    def from_batch(cls, batch: Batch) -> BatchDetailOut:
        return cls(
            **_summary_fields(batch),
            documents=[
                DocumentOut.model_validate(document) for document in batch.documents
            ],
        )


def _summary_fields(batch: Batch) -> dict:
    counts = Counter(document.status for document in batch.documents)
    document_counts = BatchDocumentCounts(
        pendente=counts.get("pendente", 0),
        processando=counts.get("processando", 0),
        concluido=counts.get("concluido", 0),
        erro=counts.get("erro", 0),
    )
    return {
        "id": batch.id,
        "status": batch.status,
        "created_at": batch.created_at,
        "finished_at": batch.finished_at,
        "total_documents": len(batch.documents),
        "processed_documents": document_counts.concluido + document_counts.erro,
        "document_counts": document_counts,
    }
