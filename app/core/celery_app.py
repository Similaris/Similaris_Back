from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "similaris",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.document_tasks"],
)

celery_app.conf.update(
    # Confirma a mensagem apenas após o término da tarefa: se um worker
    # cair no meio do processamento, outro reprocessa o documento.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Distribui os documentos do lote entre os workers disponíveis em vez
    # de deixar um único worker reservar várias mensagens de uma vez.
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
