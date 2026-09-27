from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.auth import User
from app.repositories.analysis import (
    AnalysisResultRepository,
    BatchRepository,
    DocumentRepository,
    SegmentRepository,
)
from app.schemas.analysis import (
    BatchUploadOut,
    DocumentAnalysisOut,
    DocumentOut,
    SegmentOut,
)
from app.services.analysis.analysis_report import AnalysisReportService
from app.services.documents import (
    FileTooLargeError,
    UnsupportedDocumentTypeError,
    UploadFilePayload,
    UploadService,
    UploadValidationError,
    dispatch_document_processing,
)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _read_upload(file: UploadFile) -> bytes:
    max_bytes = settings.upload_max_file_size_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise FileTooLargeError(
            f"O arquivo {file.filename or 'sem nome'} excede o limite de "
            f"{settings.upload_max_file_size_mb} MB."
        )
    return content


@router.post("/upload", response_model=BatchUploadOut, status_code=201)
async def upload_documents(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recebe PDF/DOCX, cria o lote e enfileira o processamento."""
    try:
        payloads = [
            UploadFilePayload(filename=file.filename or "", content=await _read_upload(file))
            for file in files
        ]
        result = await run_in_threadpool(
            UploadService(db).upload_documents, current_user.id, payloads
        )
    except FileTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error))
    except UnsupportedDocumentTypeError as error:
        raise HTTPException(status_code=415, detail=str(error))
    except UploadValidationError as error:
        raise HTTPException(status_code=400, detail=str(error))

    return BatchUploadOut(
        batch_id=result.batch.id,
        status=result.batch.status,
        documents=[
            DocumentOut.model_validate(document) for document in result.documents
        ],
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista os documentos enviados pelo usuário autenticado."""
    return DocumentRepository(db).list_for_user(current_user.id)


@router.post("/{document_id}/retry", response_model=DocumentOut)
def retry_document_analysis(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recoloca na fila uma análise que terminou com erro."""
    documents = DocumentRepository(db)
    document = documents.get_by_id_for_user(document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if document.status != "erro":
        raise HTTPException(
            status_code=409,
            detail="Somente documentos com erro podem ser reenviados.",
        )

    AnalysisResultRepository(db).delete_by_document(document.id)
    document.status = "pendente"
    document.error_message = None
    document.started_at = None
    document.finished_at = None
    document.plagiarism_percent = None
    document.extraction_ms = None
    document.lexical_ms = None
    document.semantic_ms = None
    document.analysis_profile = None
    document.reference_fingerprint = None
    document.batch.status = "pendente"
    document.batch.finished_at = None
    documents.save(document)
    BatchRepository(db).save(document.batch)

    try:
        dispatch_document_processing(document.id)
    except Exception:
        document.status = "erro"
        document.error_message = "Não foi possível reenviar o documento para processamento."
        document.finished_at = datetime.now(UTC)
        document.batch.status = "erro"
        document.batch.finished_at = document.finished_at
        documents.save(document)
        BatchRepository(db).save(document.batch)
        raise HTTPException(status_code=503, detail=document.error_message)
    return document


@router.get("/{document_id}/segments", response_model=list[SegmentOut])
def list_document_segments(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista os segmentos de um documento do usuário autenticado."""
    document = DocumentRepository(db).get_by_id_for_user(
        document_id, current_user.id
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    return SegmentRepository(db).list_by_document(document_id)


@router.get("/{document_id}/analysis", response_model=DocumentAnalysisOut)
def get_document_analysis(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna status, agregados e correspondencias da analise do documento."""
    document = DocumentRepository(db).get_by_id_for_user(
        document_id, current_user.id
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")

    analysis = AnalysisReportService(db).build_document_analysis(document)
    return DocumentAnalysisOut.from_analysis(document, analysis)
