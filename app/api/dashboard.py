from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.schemas.analysis.dashboard import DashboardOut
from app.services.analysis.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna os indicadores agregados do usuario autenticado."""
    return DashboardService(db).build(current_user.id)
