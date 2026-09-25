from app.core import database
from app.core.celery_app import celery_app
from app.services.documents.document_processing import DocumentProcessingService
from app.services.documents.exceptions import RetryableDocumentProcessingError

MAX_RETRIES = 3
RETRY_BASE_SECONDS = 5


@celery_app.task(bind=True, name="documents.process_document", max_retries=MAX_RETRIES)
def process_document(self, document_id: int) -> None:
    """Processa um documento do lote em um worker Celery."""
    db = database.SessionLocal()
    try:
        service = DocumentProcessingService(db)
        try:
            service.process_document(document_id)
        except RetryableDocumentProcessingError as error:
            if self.request.retries >= self.max_retries:
                service.mark_failed_after_retries(document_id, str(error))
                raise
            countdown = RETRY_BASE_SECONDS * (2 ** self.request.retries)
            raise self.retry(exc=error, countdown=countdown)
        except Exception as error:
            message = f"Falha inesperada no processamento: {type(error).__name__}"
            if self.request.retries >= self.max_retries:
                service.mark_failed_after_retries(document_id, message)
                raise
            countdown = RETRY_BASE_SECONDS * (2 ** self.request.retries)
            raise self.retry(exc=error, countdown=countdown)
    finally:
        db.close()
