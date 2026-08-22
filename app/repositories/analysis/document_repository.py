from sqlalchemy.orm import Session

from app.models.analysis import Batch, Document


class DocumentRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id_for_user(
        self, document_id: int, user_id: int
    ) -> Document | None:
        return (
            self.db.query(Document)
            .join(Document.batch)
            .filter(
                Document.id == document_id,
                Batch.user_id == user_id,
            )
            .first()
        )
