from datetime import datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_batches: int
    total_documents: int
    completed_batches: int
    processing_batches: int


class BatchStatusDistribution(BaseModel):
    pendente: int = 0
    processando: int = 0
    concluido: int = 0
    erro: int = 0


class SimilarityDistribution(BaseModel):
    low: int = 0
    moderate: int = 0
    high: int = 0
    very_high: int = 0


class AnalysesByPeriod(BaseModel):
    period: str
    count: int


class RecentAnalysis(BaseModel):
    id: int
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    document_count: int


class DashboardOut(BaseModel):
    summary: DashboardSummary
    status_distribution: BatchStatusDistribution
    similarity_distribution: SimilarityDistribution
    analyses_over_time: list[AnalysesByPeriod]
    recent_analyses: list[RecentAnalysis]
