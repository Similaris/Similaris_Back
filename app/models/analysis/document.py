from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis.analysis_result import AnalysisResult
    from app.models.analysis.batch import Batch
    from app.models.analysis.segment import Segment


class Document(Base):
    """Arquivo enviado pelo usuário para análise de similaridade."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_batch_id", "batch_id"),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pendente"
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    plagiarism_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    extraction_ms: Mapped[int | None]
    lexical_ms: Mapped[int | None]
    semantic_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch: Mapped[Batch] = relationship(back_populates="documents")
    segments: Mapped[list[Segment]] = relationship(back_populates="document")
    analysis_results: Mapped[list[AnalysisResult]] = relationship(back_populates="document")
