from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.references.reference_segment import ReferenceSegment


class ReferenceDocument(Base):
    """Documento pertencente à base usada como referência de comparação."""

    __tablename__ = "reference_docs"
    __table_args__ = (Index("ix_reference_docs_source", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="pt"
    )
    file_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    segments: Mapped[list[ReferenceSegment]] = relationship(
        back_populates="reference_document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
