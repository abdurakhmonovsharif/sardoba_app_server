from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import AuthLog, Staff
from app.schemas import AuthLogRead

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/auth-logs")
def list_auth_logs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    query = db.query(AuthLog).order_by(AuthLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * size).limit(size).all()
    return {
        "pagination": {"page": page, "size": size, "total": total},
        "items": [AuthLogRead.from_orm(log) for log in logs],
    }
