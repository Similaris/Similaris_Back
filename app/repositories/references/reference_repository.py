from collections.abc import Iterator, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.references import ReferenceDocument, ReferenceSegment


class ReferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_corpus_id(
        self, source: str, corpus_id: str
    ) -> ReferenceDocument | None:
        return self.db.scalar(
            select(ReferenceDocument).where(
                ReferenceDocument.source == source,
                ReferenceDocument.corpus_id == corpus_id,
            )
        )

    def add(
        self,
        document: ReferenceDocument,
        segments: Sequence[ReferenceSegment],
    ) -> ReferenceDocument:
        document.segments = list(segments)
        self.db.add(document)
        self.db.flush()
        return document

    def iter_segments(
        self, source: str = "pan-pc-11", language: str = "en"
    ) -> Iterator[ReferenceSegment]:
        statement = (
            select(ReferenceSegment)
            .join(ReferenceSegment.reference_document)
            .options(joinedload(ReferenceSegment.reference_document))
            .where(
                ReferenceDocument.source == source,
                ReferenceDocument.language == language,
                ReferenceDocument.corpus_id.is_not(None),
            )
            .order_by(ReferenceDocument.corpus_id, ReferenceSegment.position)
            .execution_options(yield_per=256)
        )
        yield from self.db.scalars(statement)
