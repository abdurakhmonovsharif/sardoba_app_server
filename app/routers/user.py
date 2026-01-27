import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import get_current_client, get_current_manager, get_current_staff, get_db
from app.core.localization import localize_message
from app.core.storage import extract_profile_photo_name, profile_photo_path
from app.models import Staff, StaffRole, User
from app.schemas import (
    AdminUserUpdate,
    CardRead,
    CashbackRead,
    LoyaltySummary,
    UserDetail,
    UserListResponse,
    UserRead,
    UserUpdate,
    StaffRead,
)
from app.services import CashbackService, IikoProfileSyncService, UserService

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get("", response_model=UserListResponse)
def list_users(
    search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    waiter: int | None = Query(default=None, ge=1),
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> UserListResponse:
    query = (
        db.query(User)
        .options(selectinload(User.cards))
        .filter(User.is_deleted == False)  # noqa: E712
    )

    if staff.role == StaffRole.MANAGER:
        target_waiter = waiter
    else:
        target_waiter = staff.id
        if waiter is not None and waiter != staff.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=localize_message("Forbidden"),
            )

    if target_waiter is not None:
        query = query.filter(User.waiter_id == target_waiter)
   
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
    is_waiter_request = staff.role == StaffRole.WAITER
    zero_balance = Decimal("0")
    user_items: list[UserRead] = []
    for user in users:
        user_payload = UserRead.from_orm(user)
        # Attach all cards for admin/manager; waiters see the same since balance is already masked
        user_payload = user_payload.copy(
            update={"cards": [CardRead.from_orm(card) for card in user.cards]}
        )
        if is_waiter_request:
            # Hide actual cashback balance for waiters by always returning zero.
            user_payload = user_payload.copy(update={"cashback_balance": zero_balance})
        user_items.append(user_payload)
    return UserListResponse(
        pagination={"page": page, "size": page_size, "total": total},
        items=user_items,
    )


@router.get("/{user_id}", response_model=UserDetail)
def get_user_by_id(
    user_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> UserDetail:
    user = (
        db.query(User)
        .options(selectinload(User.waiter), selectinload(User.cards))
        .filter(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=localize_message("User not found"),
        )
    cashback_service = CashbackService(db)
    transactions = cashback_service.get_user_cashbacks(user_id=user.id)
    loyalty = cashback_service.loyalty_summary(user=user)

    user_payload = UserRead.from_orm(user).copy(
        update={"cards": [CardRead.from_orm(card) for card in user.cards]}
    )
    return UserDetail(
        **user_payload.dict(by_alias=True),
        loyalty=LoyaltySummary(**loyalty),
        transactions=[CashbackRead.from_orm(entry) for entry in transactions],
        waiter=StaffRead.from_orm(user.waiter) if user.waiter else None,
    )


@router.put("/me", response_model=UserRead)
def update_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> UserRead:
    updated = False
    iiko_updates: dict[str, Any] = {}

    if payload.name is not None:
        current_user.name = payload.name
        updated = True
        if payload.name:
            iiko_updates["fullName"] = payload.name
    if payload.surname is not None:
        current_user.surname = payload.surname or None
        updated = True
        if payload.surname:
            iiko_updates["surname"] = payload.surname
    if payload.middle_name is not None:
        current_user.middle_name = payload.middle_name or None
        updated = True
        if payload.middle_name:
            iiko_updates["middleName"] = payload.middle_name
    if payload.date_of_birth is not None:
        current_user.date_of_birth = payload.date_of_birth
        updated = True
        iiko_updates["birthday"] = payload.date_of_birth.strftime("%Y-%m-%dT00:00:00.000")
    if payload.profile_photo_url is not None:
        current_user.profile_photo_url = payload.profile_photo_url or None
        updated = True
    if payload.email is not None:
        current_user.email = payload.email or None
        updated = True
        if payload.email:
            iiko_updates["email"] = payload.email
    if payload.gender is not None:
        current_user.gender = payload.gender or None
        updated = True
        if payload.gender:
            iiko_updates["sex"] = payload.gender

    if not updated:
        return UserRead.from_orm(current_user)

    db.add(current_user)
    if iiko_updates:
        composed_full_name = " ".join(
            part.strip()
            for part in (current_user.name, current_user.middle_name, current_user.surname)
            if isinstance(part, str) and part.strip()
        ).strip()
        if composed_full_name and "fullName" not in iiko_updates:
            iiko_updates["fullName"] = composed_full_name

    sync_service = IikoProfileSyncService(db)
    if iiko_updates or current_user.pending_iiko_profile_update:
        sync_service.sync_profile_updates(current_user, iiko_updates or None)

    db.commit()
    db.refresh(current_user)

    return UserRead.from_orm(current_user)


@router.patch("/{user_id}", response_model=UserDetail)
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> UserDetail:
    user = (
        db.query(User)
        .options(selectinload(User.waiter))
        .filter(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=localize_message("User not found"),
        )

    updated = False
    first = payload.first_name.strip() if payload.first_name else None
    last = payload.last_name.strip() if payload.last_name else None
    middle = payload.middleName.strip() if payload.middleName else None
    if first or last or middle:
        parts = [part for part in (first, middle, last) if part]
        full_name = " ".join(parts)
        if full_name:
            user.name = full_name
            updated = True
        if last is not None:
            user.surname = last or None
            updated = True
        if middle is not None:
            user.middle_name = middle or None
            updated = True
    if payload.dob is not None:
        user.date_of_birth = payload.dob
        updated = True
    if payload.profile_photo_url is not None:
        user.profile_photo_url = payload.profile_photo_url or None
        updated = True
    if payload.giftget is not None:
        user.giftget = payload.giftget
        updated = True
    if payload.waiter_id is not None:
        waiter = (
            db.query(Staff)
            .filter(Staff.id == payload.waiter_id, Staff.role == StaffRole.WAITER)
            .first()
        )
        if not waiter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=localize_message("Waiter not found"),
            )
        user.waiter = waiter
        updated = True

    if updated:
        db.add(user)
        db.commit()
        db.refresh(user)
    cashback_service = CashbackService(db)
    transactions = cashback_service.get_user_cashbacks(user_id=user.id)
    loyalty = cashback_service.loyalty_summary(user=user)

    user_payload = UserRead.from_orm(user)
    return UserDetail(
        **user_payload.dict(by_alias=True),
        loyalty=LoyaltySummary(**loyalty),
        transactions=[CashbackRead.from_orm(entry) for entry in transactions],
        waiter=StaffRead.from_orm(user.waiter) if user.waiter else None,
    )


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
    UserService(db).delete_user(current_user)
