from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult, Batch, Document


@dataclass(frozen=True, slots=True)
class PeriodCount:
    year: int
    month: int
    count: int


@dataclass(frozen=True, slots=True)
class RecentBatch:
    id: int
    status: str
    created_at: datetime
    finished_at: datetime | None
    document_count: int


class DashboardRepository:

    def __init__(self, db: Session):
        self.db = db

    def count_batches_by_status(self, user_id: int) -> dict[str, int]:
        rows = (
            self.db.query(Batch.status, func.count(Batch.id))
            .filter(Batch.user_id == user_id)
            .group_by(Batch.status)
            .all()
        )
        return {status: count for status, count in rows}

    def count_documents(self, user_id: int) -> int:
        return (
            self.db.query(func.count(Document.id))
            .join(Document.batch)
            .filter(Batch.user_id == user_id)
            .scalar()
            or 0
        )

    def count_results_by_classification(self, user_id: int) -> dict[str, int]:
        rows = (
            self.db.query(
                AnalysisResult.plagiarism_type,
                func.count(AnalysisResult.id),
            )
            .join(AnalysisResult.document)
            .join(Document.batch)
            .filter(Batch.user_id == user_id)
            .group_by(AnalysisResult.plagiarism_type)
            .all()
        )
        return {classification: count for classification, count in rows}

    def count_batches_by_month(self, user_id: int) -> list[PeriodCount]:
        year = extract("year", Batch.created_at)
        month = extract("month", Batch.created_at)
        rows = (
            self.db.query(year, month, func.count(Batch.id))
            .filter(Batch.user_id == user_id)
            .group_by(year, month)
            .order_by(year, month)
            .all()
        )
        return [
            PeriodCount(year=int(row_year), month=int(row_month), count=count)
            for row_year, row_month, count in rows
        ]

    def list_recent_batches(
        self, user_id: int, limit: int = 5
    ) -> list[RecentBatch]:
        rows = (
            self.db.query(
                Batch.id,
                Batch.status,
                Batch.created_at,
                Batch.finished_at,
                func.count(Document.id),
            )
            .outerjoin(Batch.documents)
            .filter(Batch.user_id == user_id)
            .group_by(
                Batch.id,
                Batch.status,
                Batch.created_at,
                Batch.finished_at,
            )
            .order_by(Batch.created_at.desc(), Batch.id.desc())
            .limit(limit)
            .all()
        )
        return [RecentBatch(*row) for row in rows]
