from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis.analysis_result import AnalysisResult
    from app.models.references.reference_document import ReferenceDocument


class ReferenceSegment(Base):
    """Trecho pré-processado da base de referência."""

    __tablename__ = "reference_segments"
    __table_args__ = (
        UniqueConstraint("reference_doc_id", "position"),
        Index("ix_reference_segments_doc_id", "reference_doc_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_doc_id: Mapped[int] = mapped_column(
        ForeignKey("reference_docs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    text_original: Mapped[str] = mapped_column(Text, nullable=False)
    text_clean: Mapped[str | None] = mapped_column(Text)

    reference_document: Mapped[ReferenceDocument] = relationship(
        back_populates="segments"
    )
    analysis_results: Mapped[list[AnalysisResult]] = relationship(
        back_populates="reference_segment"
    )
