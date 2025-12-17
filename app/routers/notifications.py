from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.dependencies import get_current_client, get_current_manager, get_db
from app.core.localization import localize_message
from app.core.notification_ws import notification_ws_manager
from app.core.security import decode_access_token
from app.models import Staff, User, UserNotification
from app.schemas import (
    AdminNotificationCreate,
    NotificationCreate,
    NotificationListResponse,
    NotificationRead,
    NotificationTokenRegister,
    NotificationUpdate,
    UserNotificationRead,
)
from app.services import (
    NotificationService,
    NotificationTokenService,
    PushNotificationService,
    UserNotificationService,
)
from app.services.user_notification_service import AUTO_NOTIFICATION_TYPES
from app.services import exceptions as service_exceptions
from app.models.enums import AuthActorType

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def _notification_payload(notification: UserNotification) -> dict:
    return {
        "notification_id": notification.id,
        "title": notification.title,
        "description": notification.description,
        "payload": notification.payload or {},
        "language": notification.language,
        "type": notification.type,
    }


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    service = NotificationService(db)
    total, items = service.list_notifications(page=page, size=page_size)
    return NotificationListResponse(
        pagination={"page": page, "size": page_size, "total": total},
        items=[NotificationRead.from_orm(item) for item in items],
    )


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
def get_notification(
    notification_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> NotificationRead:
    service = NotificationService(db)
    try:
        notification = service.get_notification(notification_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    return NotificationRead.from_orm(notification)


@router.put("/{notification_id}", response_model=NotificationRead)
@router.patch("/{notification_id}", response_model=NotificationRead)
def update_notification(
    notification_id: int,
    payload: NotificationUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> NotificationRead:
    data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("No fields provided for update")
        )
    service = NotificationService(db)
    try:
        notification = service.update_notification(actor=manager, notification_id=notification_id, data=data)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc


@router.post("/register-token", status_code=status.HTTP_204_NO_CONTENT)
def register_token(
    payload: NotificationTokenRegister,
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> None:
    service = NotificationTokenService(db)
    service.register_token(
        user_id=current_user.id,
        device_token=payload.deviceToken,
        device_type=payload.deviceType,
        language=payload.language,
    )


@router.get("/me", response_model=list[UserNotificationRead])
def list_my_notifications(
    limit: int | None = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> list[UserNotificationRead]:
    service = UserNotificationService(db)
    notifications = service.list_for_user(user_id=current_user.id, limit=limit)
    return [UserNotificationRead.from_orm(item) for item in notifications]


@router.post("/send", status_code=status.HTTP_204_NO_CONTENT)
def send_admin_notification(
    payload: AdminNotificationCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> None:
    dispatcher = PushNotificationService(db)
    for user_id in set(payload.userIds):
        dispatcher.send_admin_notification(
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            notification_type=payload.notificationType,
            payload=payload.payload or {},
            language=payload.language,
        )


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket) -> None:
    token = _extract_bearer_token(websocket.headers.get("authorization"))
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    actor_type = payload.get("actor_type") or payload.get("type")
    if actor_type != AuthActorType.CLIENT.value:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id = int(payload["sub"])
    db_session = get_session_factory()()
    try:
        user = db_session.query(User).filter(User.id == user_id, User.is_deleted == False).first()
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        service = UserNotificationService(db_session)
        await notification_ws_manager.connect(user_id, websocket)
        try:
            pending = service.list_pending_for_user(user_id)
            for notification in pending:
                await websocket.send_json(_notification_payload(notification))
                service.mark_as_sent(notification.id)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await notification_ws_manager.disconnect(user_id, websocket)
    finally:
        db_session.close()
