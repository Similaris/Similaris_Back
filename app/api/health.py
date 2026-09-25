from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.references import ReferenceDocument, ReferenceSegment

router = APIRouter(tags=["health"])


def _redis_ready() -> bool:
    try:
        from redis import Redis

        connection = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            return bool(connection.ping())
        finally:
            connection.close()
    except Exception:
        return False


def _workers_ready() -> bool:
    try:
        return bool(celery_app.control.ping(timeout=1.0))
    except Exception:
        return False


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
    }


@router.get("/ready")
def readiness_check():
    """Confirma que a infraestrutura necessária para analisar está pronta."""
    checks: dict[str, bool] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            checks["database"] = True
            checks["reference_documents"] = (
                db.scalar(select(func.count(ReferenceDocument.id))) or 0
            ) > 0
            checks["reference_segments"] = (
                db.scalar(select(func.count(ReferenceSegment.id))) or 0
            ) > 0
    except Exception:
        checks["database"] = False
        checks["reference_documents"] = False
        checks["reference_segments"] = False

    checks["redis"] = _redis_ready()
    checks["workers"] = _workers_ready()

    checks["reference_index"] = (
        Path(settings.reference_index_dir) / "current.json"
    ).is_file()
    if not all(checks.values()):
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
