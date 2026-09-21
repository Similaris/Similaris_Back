from sqlalchemy.orm import Session

from app.repositories.analysis.dashboard_repository import DashboardRepository
from app.schemas.analysis.dashboard import (
    AnalysesByPeriod,
    BatchStatusDistribution,
    DashboardOut,
    DashboardSummary,
    RecentAnalysis,
    SimilarityDistribution,
)


class DashboardService:

    def __init__(
        self,
        db: Session,
        repository: DashboardRepository | None = None,
    ):
        self.repository = repository or DashboardRepository(db)

    def build(self, user_id: int) -> DashboardOut:
        status_counts = self.repository.count_batches_by_status(user_id)
        classification_counts = (
            self.repository.count_results_by_classification(user_id)
        )
        periods = self.repository.count_batches_by_month(user_id)
        recent_batches = self.repository.list_recent_batches(user_id)

        return DashboardOut(
            summary=DashboardSummary(
                total_batches=sum(status_counts.values()),
                total_documents=self.repository.count_documents(user_id),
                completed_batches=status_counts.get("concluido", 0),
                processing_batches=status_counts.get("processando", 0),
            ),
            status_distribution=BatchStatusDistribution(
                pendente=status_counts.get("pendente", 0),
                processando=status_counts.get("processando", 0),
                concluido=status_counts.get("concluido", 0),
                erro=status_counts.get("erro", 0),
            ),
            similarity_distribution=SimilarityDistribution(
                low=classification_counts.get("LOW", 0),
                moderate=classification_counts.get("MODERATE", 0),
                high=classification_counts.get("HIGH", 0),
                very_high=classification_counts.get("VERY_HIGH", 0),
            ),
            analyses_over_time=[
                AnalysesByPeriod(
                    period=f"{period.year:04d}-{period.month:02d}",
                    count=period.count,
                )
                for period in periods
            ],
            recent_analyses=[
                RecentAnalysis(
                    id=batch.id,
                    status=batch.status,
                    created_at=batch.created_at,
                    finished_at=batch.finished_at,
                    document_count=batch.document_count,
                )
                for batch in recent_batches
            ],
        )
