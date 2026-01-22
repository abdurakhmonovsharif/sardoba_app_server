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


@router.post("/sync/users")
def sync_users_with_iiko(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
    batch_size: int = Query(default=500, ge=1, le=5_000),
) -> dict:
    """
    Sync all active users with iiko `/customer/info`.
    Intended for admin panel trigger or periodic calls (e.g., every 10 minutes).
    """
    service = AuthService(db)
    synced = 0
    failed: list[dict] = []

    # Process users in batches to keep memory bounded.
    offset = 0
    while True:
        users = (
            db.query(User)
            .filter(User.is_deleted == False)  # noqa: E712
            .order_by(User.id)
            .offset(offset)
            .limit(batch_size)
            .all()
        )
        if not users:
            break

        for user in users:
            try:
                service.sync_user_from_iiko(user)
                db.flush()
                synced += 1
            except Exception as exc:  # pragma: no cover - admin maintenance endpoint
                db.rollback()
                failed.append({"user_id": user.id, "phone": user.phone, "error": str(exc)})
                continue

        db.commit()
        offset += batch_size

    return {"synced": synced, "failed": failed, "failed_count": len(failed)}
