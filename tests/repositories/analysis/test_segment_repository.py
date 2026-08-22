from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.analysis import Batch, Document, Segment
from app.models.auth import User
from app.repositories.analysis import SegmentRepository


def test_list_by_document_for_user_does_not_expose_another_users_segments():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        owner = User(name="Owner", email="owner@example.com", password_hash="hash")
        other_user = User(
            name="Other", email="other@example.com", password_hash="hash"
        )
        db.add_all([owner, other_user])
        db.flush()

        owner_batch = Batch(user_id=owner.id)
        other_batch = Batch(user_id=other_user.id)
        db.add_all([owner_batch, other_batch])
        db.flush()

        owner_document = Document(
            batch_id=owner_batch.id,
            filename="owner.pdf",
            file_type="pdf",
            file_path="owner.pdf",
        )
        other_document = Document(
            batch_id=other_batch.id,
            filename="other.pdf",
            file_type="pdf",
            file_path="other.pdf",
        )
        db.add_all([owner_document, other_document])
        db.flush()

        db.add_all(
            [
                Segment(
                    document_id=owner_document.id,
                    position=1,
                    text_original="Trecho do proprietário.",
                ),
                Segment(
                    document_id=other_document.id,
                    position=1,
                    text_original="Trecho de outro usuário.",
                ),
            ]
        )
        db.commit()

        repository = SegmentRepository(db)

        assert repository.list_by_document_for_user(
            owner_document.id, owner.id
        )[0].text_original == "Trecho do proprietário."
        assert repository.list_by_document_for_user(
            other_document.id, owner.id
        ) == []
