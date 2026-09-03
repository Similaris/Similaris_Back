from sqlalchemy.orm import Session, selectinload

from app.models.analysis import Batch


class BatchRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_for_user(self, user_id: int) -> Batch:
        batch = Batch(user_id=user_id)
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def save(self, batch: Batch) -> Batch:
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def get_by_id_for_user(self, batch_id: int, user_id: int) -> Batch | None:
        return (
            self.db.query(Batch)
            .options(selectinload(Batch.documents))
            .filter(Batch.id == batch_id, Batch.user_id == user_id)
            .first()
        )

    def list_for_user(self, user_id: int) -> list[Batch]:
        return (
            self.db.query(Batch)
            .options(selectinload(Batch.documents))
            .filter(Batch.user_id == user_id)
            .order_by(Batch.created_at.desc(), Batch.id.desc())
            .all()
        )
