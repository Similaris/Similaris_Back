from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.repositories.analysis import BatchRepository
from app.schemas.analysis import (
    BatchAnalysisOut,
    BatchDetailOut,
    BatchSummaryOut,
    DocumentAnalysisOut,
)
from app.services.analysis.analysis_report import AnalysisReportService

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("", response_model=list[BatchSummaryOut])
def list_batches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista os lotes do usuário com o resumo do processamento."""
    batches = BatchRepository(db).list_for_user(current_user.id)
    return [BatchSummaryOut.from_batch(batch) for batch in batches]


@router.get("/{batch_id}", response_model=BatchDetailOut)
def get_batch(
    batch_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detalha um lote com o andamento de cada documento."""
    batch = BatchRepository(db).get_by_id_for_user(batch_id, current_user.id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")

    return BatchDetailOut.from_batch(batch)


@router.get("/{batch_id}/analysis", response_model=BatchAnalysisOut)
def get_batch_analysis(
    batch_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna as analises de todos os documentos de um lote."""
    batch = BatchRepository(db).get_by_id_for_user(batch_id, current_user.id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Lote nao encontrado.")

    report_service = AnalysisReportService(db)
    return BatchAnalysisOut(
        batch_id=batch.id,
        status=batch.status,
        documents=[
            DocumentAnalysisOut.from_analysis(
                document,
                report_service.build_document_analysis(document),
            )
            for document in batch.documents
        ],
    )
