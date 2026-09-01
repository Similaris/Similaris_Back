from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.repositories.analysis import DocumentRepository, SegmentRepository
from app.schemas.analysis import (
    BatchUploadOut,
    DocumentOut,
    SegmentOut,
)
from app.services.documents import (
    FileTooLargeError,
    UnsupportedDocumentTypeError,
    UploadFilePayload,
    UploadService,
    UploadValidationError,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=BatchUploadOut, status_code=201)
async def upload_documents(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recebe PDF/DOCX, cria o lote e enfileira o processamento."""
    payloads = [
        UploadFilePayload(filename=file.filename or "", content=await file.read())
        for file in files
    ]

    try:
        result = UploadService(db).upload_documents(current_user.id, payloads)
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
