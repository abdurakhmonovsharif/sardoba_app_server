from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import AuthLog, Staff, User
from app.schemas import AuthLogRead
from app.services.auth_service import AuthService

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


@router.post("/sync/users/{user_id}")
def sync_single_user_with_iiko(
    user_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> dict:
    """
    Sync exactly one user with iiko: fetch info, or create if missing, then resync.
    Useful for manual recovery when only one user's data is out of sync.
    """
    user = (
        db.query(User)
        .filter(User.id == user_id, User.is_deleted == False)  # noqa: E712
        .first()
    )
    if not user:
        return {"success": False, "error": "User not found or deleted"}

    service = AuthService(db)
    try:
        service.sync_user_from_iiko(user, create_if_missing=True)
        db.commit()
    except Exception as exc:  # pragma: no cover - admin maintenance endpoint
        db.rollback()
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "user_id": user.id,
        "phone": user.phone,
        "iiko_customer_id": user.iiko_customer_id,
        "iiko_wallet_id": user.iiko_wallet_id,
    }
