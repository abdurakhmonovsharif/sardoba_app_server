from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import AuthActorType, AuthLog, AuthAction, Staff, User
from app.schemas import AuthLogActor, AuthLogListResponse, AuthLogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/auth", response_model=AuthLogListResponse)
def list_auth_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="page_size"),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    query = db.query(AuthLog).order_by(AuthLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * page_size).limit(page_size).all()

    staff_ids = [log.actor_id for log in logs if log.actor_type == AuthActorType.STAFF and log.actor_id]
    user_ids = [log.actor_id for log in logs if log.actor_type == AuthActorType.CLIENT and log.actor_id]

    staff_map = {}
    if staff_ids:
        staff_map = {staff.id: staff for staff in db.query(Staff).filter(Staff.id.in_(staff_ids)).all()}

    user_map = {}
    if user_ids:
        user_map = {user.id: user for user in db.query(User).filter(User.id.in_(user_ids)).all()}

    def _actor_type_name(actor_type: AuthActorType) -> str:
        if actor_type == AuthActorType.STAFF:
            return "staff"
        if actor_type == AuthActorType.CLIENT:
            return "user"
        return str(actor_type).lower()

    def _event_name(action: AuthAction) -> str:
        mapping = {
            AuthAction.LOGIN: "login_success",
            AuthAction.LOGOUT: "logout",
            AuthAction.OTP_REQUEST: "otp_request",
            AuthAction.OTP_VERIFICATION: "otp_verification",
            AuthAction.FAILED_LOGIN: "login_failed",
        }
        return mapping.get(action, str(action).lower())

    items: list[AuthLogRead] = []
    for log in logs:
        actor: AuthLogActor | None = None
        actor_type_str = _actor_type_name(log.actor_type)
        if log.actor_type == AuthActorType.STAFF:
            staff = staff_map.get(log.actor_id)
            actor = AuthLogActor(
                id=log.actor_id,
                type=actor_type_str,
                name=staff.name if staff else None,
                phone=staff.phone if staff else log.phone,
                role=staff.role.value.lower() if staff and staff.role else None,
            )
        elif log.actor_type == AuthActorType.CLIENT:
            user = user_map.get(log.actor_id)
            actor = AuthLogActor(
                id=log.actor_id,
                type=actor_type_str,
                name=user.name if user else None,
                phone=user.phone if user else log.phone,
            )
        else:
            actor = AuthLogActor(
                id=log.actor_id,
                type=actor_type_str,
                phone=log.phone,
            )

        meta = log.meta or {}
        status_override = meta.get("status")
        status = status_override or ("failed" if log.action == AuthAction.FAILED_LOGIN else "success")

        items.append(
            AuthLogRead(
                id=log.id,
                actor_type=actor_type_str,
                actor_id=log.actor_id,
                event=_event_name(log.action),
                status=status,
                phone=log.phone,
                action=log.action.value if hasattr(log.action, "value") else str(log.action),
                ip=log.ip,
                user_agent=log.user_agent,
                metadata=meta or None,
                user=actor,
                created_at=log.created_at,
            )
        )

    return {
        "pagination": {"page": page, "size": page_size, "total": total},
        "items": items,
    }
