from sqlalchemy.orm import Session

from app.models.analysis import Batch, Document


class DocumentRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def save(self, document: Document) -> Document:
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self.db.get(Document, document_id)

    def list_by_batch(self, batch_id: int) -> list[Document]:
        return (
            self.db.query(Document)
            .filter(Document.batch_id == batch_id)
            .order_by(Document.id)
            .all()
        )

    def list_for_user(self, user_id: int) -> list[Document]:
        return (
            self.db.query(Document)
            .join(Document.batch)
            .filter(Batch.user_id == user_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .all()
        )

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
