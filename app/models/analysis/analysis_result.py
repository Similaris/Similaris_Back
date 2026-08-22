from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis.document import Document
    from app.models.analysis.segment import Segment
    from app.models.references.reference_segment import ReferenceSegment


class AnalysisResult(Base):

    __tablename__ = "analysis_results"
    __table_args__ = (
        Index("ix_analysis_results_document_id", "document_id"),
        Index("ix_analysis_results_segment_id", "segment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", ondelete="CASCADE"), nullable=False
    )
    reference_segment_id: Mapped[int] = mapped_column(
        ForeignKey("reference_segments.id", ondelete="CASCADE"), nullable=False
    )
    lexical_cosine: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    lexical_jaccard: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    semantic_cosine: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    final_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    plagiarism_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="analysis_results")
    segment: Mapped[Segment] = relationship(back_populates="analysis_results")
    reference_segment: Mapped[ReferenceSegment] = relationship(
        back_populates="analysis_results"
    )
