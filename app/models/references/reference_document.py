from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.references.reference_segment import ReferenceSegment


class ReferenceDocument(Base):

    __tablename__ = "reference_docs"
    __table_args__ = (
        Index("ix_reference_docs_source", "source"),
        UniqueConstraint(
            "source", "corpus_id", name="uq_reference_docs_source_corpus_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="en"
    )
    file_path: Mapped[str | None] = mapped_column(String(500))
    corpus_id: Mapped[str | None] = mapped_column(String(500))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    import_signature: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    segments: Mapped[list[ReferenceSegment]] = relationship(
        back_populates="reference_document"
    )
