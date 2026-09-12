from collections.abc import Iterator, Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.references import ReferenceDocument, ReferenceSegment

REFERENCE_BATCH_SIZE = 256


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
            self._segments_statement(source, language)
            .order_by(ReferenceDocument.corpus_id, ReferenceSegment.position)
            .execution_options(yield_per=REFERENCE_BATCH_SIZE, populate_existing=True)
        )
        yield from self.db.scalars(statement)

    def get_segments_by_ids(
        self,
        segment_ids: Sequence[int],
        source: str = "pan-pc-11",
        language: str = "en",
    ) -> list[ReferenceSegment]:
        ids = list(dict.fromkeys(segment_ids))
        segments: list[ReferenceSegment] = []
        for start in range(0, len(ids), REFERENCE_BATCH_SIZE):
            statement = (
                self._segments_statement(source, language)
                .where(ReferenceSegment.id.in_(ids[start : start + REFERENCE_BATCH_SIZE]))
                .order_by(ReferenceSegment.id)
                .execution_options(populate_existing=True)
            )
            segments.extend(self.db.scalars(statement))
        return segments

    @staticmethod
    def _segments_statement(
        source: str, language: str
    ) -> Select[tuple[ReferenceSegment]]:
        return (
            select(ReferenceSegment)
            .join(ReferenceSegment.reference_document)
            .options(joinedload(ReferenceSegment.reference_document))
            .where(
                ReferenceDocument.source == source,
                ReferenceDocument.language == language,
                ReferenceDocument.corpus_id.is_not(None),
            )
        )
