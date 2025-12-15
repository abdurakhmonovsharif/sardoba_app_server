from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.core.localization import localize_message
from app.models import Staff
from app.schemas import StaffListResponse, StaffRead, WaiterCreateRequest, WaiterUpdateRequest
from app.services import StaffService
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/waiters", tags=["waiters"])


@router.get("", response_model=StaffListResponse)
def list_waiters(
    search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffListResponse:
    service = StaffService(db)
    total, waiters = service.list_waiters(page=page, size=size, search=search)
    return StaffListResponse(
        pagination={"page": page, "size": size, "total": total},
        items=[StaffRead.from_orm(waiter) for waiter in waiters],
    )


@router.post("", response_model=StaffRead, status_code=status.HTTP_201_CREATED)
def create_waiter(
    payload: WaiterCreateRequest,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffRead:
    branch_id = int(payload.branch_id) if payload.branch_id is not None else None
    service = StaffService(db)
    try:
        waiter = service.create_waiter(
            name=payload.name,
            phone=payload.phone,
            password=payload.password,
            branch_id=branch_id,
            referring_code=payload.referral_code.strip() if payload.referral_code else None,
            actor=manager,
        )
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc
    return StaffRead.from_orm(waiter)


@router.get("/{waiter_id}", response_model=StaffRead)
def get_waiter(
    waiter_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffRead:
    service = StaffService(db)
    try:
        waiter = service.get_waiter(waiter_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    return StaffRead.from_orm(waiter)


@router.put("/{waiter_id}", response_model=StaffRead)
def update_waiter(
    waiter_id: int,
    payload: WaiterUpdateRequest,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffRead:
    data = payload.dict(exclude_unset=True)
    branch_is_set = "branch_id" in data
    branch_id = int(data["branch_id"]) if branch_is_set and data["branch_id"] is not None else None
    service = StaffService(db)
    try:
        waiter = service.update_waiter(
            waiter_id=waiter_id,
            name=data.get("name"),
            phone=data.get("phone"),
            password=data.get("password"),
            branch_id=branch_id,
            branch_is_set=branch_is_set,
            referral_code=data.get("referral_code"),
            referral_code_is_set="referral_code" in data,
        )
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc
    return StaffRead.from_orm(waiter)


@router.delete("/{waiter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_waiter(
    waiter_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> None:
    service = StaffService(db)
    try:
        service.delete_waiter(waiter_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc
