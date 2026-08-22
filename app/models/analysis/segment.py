from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis.analysis_result import AnalysisResult
    from app.models.analysis.document import Document


class Segment(Base):

    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        Index("ix_segments_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    start_offset: Mapped[int | None]
    end_offset: Mapped[int | None]
    text_original: Mapped[str] = mapped_column(Text, nullable=False)
    text_clean: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="segments")
    analysis_results: Mapped[list[AnalysisResult]] = relationship(back_populates="segment")
