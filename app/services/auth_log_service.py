from typing import Any

from sqlalchemy.orm import Session

from app.models import AuthAction, AuthActorType, AuthLog


def log_auth_event(
    *,
    db: Session,
    actor_type: AuthActorType,
    action: AuthAction,
    actor_id: int | None = None,
    phone: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuthLog:
    log = AuthLog(
        actor_type=actor_type,
        action=action,
        actor_id=actor_id,
        phone=phone,
        ip=ip,
        user_agent=user_agent,
        meta=meta,
    )
    db.add(log)
    db.flush()
    return log
