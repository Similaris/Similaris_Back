from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.analysis import Batch, Document, Segment


class SegmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: int) -> list[Segment]:
        return (
            self.db.query(Segment)
            .filter(Segment.document_id == document_id)
            .order_by(Segment.position)
            .all()
        )

    def list_by_document_for_user(
        self, document_id: int, user_id: int
    ) -> list[Segment]:
        return (
            self.db.query(Segment)
            .join(Segment.document)
            .join(Document.batch)
            .filter(
                Segment.document_id == document_id,
                Batch.user_id == user_id,
            )
            .order_by(Segment.position)
            .all()
        )

    def replace_for_document(
        self, document_id: int, segments: Sequence[Segment]
    ) -> list[Segment]:
        self.db.query(Segment).filter(Segment.document_id == document_id).delete(
            synchronize_session=False
        )

        for segment in segments:
            segment.document_id = document_id
        self.db.add_all(list(segments))
        self.db.commit()
        return list(segments)
