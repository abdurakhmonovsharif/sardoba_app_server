from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_client, get_current_manager, get_db
from app.core.storage import extract_profile_photo_name, profile_photo_path
from app.models import Staff, User
from app.schemas import UserListResponse, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(
    search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> UserListResponse:
    query = db.query(User)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(User.name.ilike(pattern), User.phone.ilike(pattern)))
    total = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return UserListResponse(
        pagination={"page": page, "size": page_size, "total": total},
        items=[UserRead.from_orm(user) for user in users],
    )


@router.put("/me", response_model=UserRead)
def update_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> UserRead:
    updated = False
    if payload.name is not None:
        current_user.name = payload.name
        updated = True
    if payload.date_of_birth is not None:
        current_user.date_of_birth = payload.date_of_birth
        updated = True
    if payload.profile_photo_url is not None:
        current_user.profile_photo_url = payload.profile_photo_url or None
        updated = True

    if not updated:
        return UserRead.from_orm(current_user)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserRead.from_orm(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> None:
    photo_name = extract_profile_photo_name(current_user.profile_photo_url)
    if photo_name:
        path = profile_photo_path(photo_name)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    db.delete(current_user)
    db.commit()
