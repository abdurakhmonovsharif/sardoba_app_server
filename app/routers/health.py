from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas import SystemHealth
from app.services import DashboardService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=list[SystemHealth])
def health_check(db: Session = Depends(get_db)):
    service = DashboardService(db)
    return service.system_health()
