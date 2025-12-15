from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import Staff
from app.schemas import ActivityItem, DashboardMetrics
from app.services import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def dashboard_metrics(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = DashboardService(db)
    return service.get_metrics()


@router.get("/activity", response_model=list[ActivityItem])
def dashboard_activity(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = DashboardService(db)
    return service.recent_activity()
