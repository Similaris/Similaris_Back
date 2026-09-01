from app.core import database
from app.core.celery_app import celery_app
from app.services.documents.document_processing import DocumentProcessingService


@celery_app.task(name="documents.process_document")
def process_document(document_id: int) -> None:
    """Processa um documento do lote em um worker Celery."""
    db = database.SessionLocal()
    try:
        DocumentProcessingService(db).process_document(document_id)
    finally:
        db.close()
