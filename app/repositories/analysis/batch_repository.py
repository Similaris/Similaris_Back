from sqlalchemy.orm import Session

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

    def get_by_id_for_user(self, batch_id: int, user_id: int) -> Batch | None:
        return (
            self.db.query(Batch)
            .filter(Batch.id == batch_id, Batch.user_id == user_id)
            .first()
        )
