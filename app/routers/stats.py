from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import Staff
from app.schemas import TopUserStats, WaiterStats
from app.services import CashbackService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/waiters", response_model=list[WaiterStats])
def waiter_stats(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CashbackService(db)
    rows = service.waiter_stats()
    return [WaiterStats(**row) for row in rows]


@router.get("/users/top", response_model=list[TopUserStats])
def top_users(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
):
    service = CashbackService(db)
    rows = service.top_users(limit=limit)
    return [TopUserStats(**row) for row in rows]
