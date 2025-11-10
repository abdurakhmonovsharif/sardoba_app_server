from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.models import Staff
from app.schemas import NotificationCreate, NotificationRead, NotificationUpdate
from app.services import NotificationService
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
def list_notifications(db: Session = Depends(get_db)):
    service = NotificationService(db)
    notifications = service.list_notifications()
    return [NotificationRead.from_orm(item) for item in notifications]


@router.post("", response_model=NotificationRead)
def create_notification(
    payload: NotificationCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = NotificationService(db)
    notification = service.create_notification(actor=manager, data=payload.dict())
    return NotificationRead.from_orm(notification)


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(notification_id: int, db: Session = Depends(get_db)) -> NotificationRead:
    service = NotificationService(db)
    try:
        notification = service.get_notification(notification_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return NotificationRead.from_orm(notification)


@router.put("/{notification_id}", response_model=NotificationRead)
def update_notification(
    notification_id: int,
    payload: NotificationUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> NotificationRead:
    data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")
    service = NotificationService(db)
    try:
        notification = service.update_notification(actor=manager, notification_id=notification_id, data=data)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return NotificationRead.from_orm(notification)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> None:
    service = NotificationService(db)
    try:
        service.delete_notification(actor=manager, notification_id=notification_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
