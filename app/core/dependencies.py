from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db_session
from app.core import security
from app.models import Staff, StaffRole, User, AuthActorType
from app.core.localization import localize_message


bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Session:
    yield from get_db_session()


def _get_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Not authenticated"))
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=localize_message("Invalid authentication scheme"),
        )
    return credentials.credentials


def get_token_payload(token: str = Depends(_get_token)) -> dict:
    try:
        payload = security.decode_access_token(token)
    except Exception as exc:  # pragma: no cover - jwt raises various exceptions
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Invalid token")
        ) from exc
    return payload


def get_current_client(db: Session = Depends(get_db), token: str = Depends(_get_token)) -> User:
    try:
        payload = security.decode_access_token(token)
    except Exception as exc:  # pragma: no cover - jwt raises various exceptions
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Invalid token")
        ) from exc

    if payload.get("actor_type") != AuthActorType.CLIENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=localize_message("Insufficient permissions")
        )

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("User not found"))
    return user


def get_current_staff(db: Session = Depends(get_db), token: str = Depends(_get_token)) -> Staff:
    try:
        payload = security.decode_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Invalid token")
        ) from exc

    if payload.get("actor_type") != AuthActorType.STAFF.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=localize_message("Insufficient permissions")
        )

    staff_id = int(payload["sub"])
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Staff not found"))
    return staff


def get_current_manager(staff: Staff = Depends(get_current_staff)) -> Staff:
    if staff.role != StaffRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=localize_message("Managers only"))
    return staff
