from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models import UserNotification

AUTO_NOTIFICATION_TYPES = {"cashback_accrual", "cashback_spent"}


class UserNotificationService:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        exclude_types: Iterable[str] | None = None,
    ) -> list[UserNotification]:
        query = (
            self.db.query(UserNotification)
            .filter(UserNotification.user_id == user_id)
            .order_by(UserNotification.created_at.desc())
        )
        if exclude_types:
            query = query.filter(~UserNotification.type.in_(exclude_types))
        if limit:
            query = query.limit(limit)
        return query.all()

    def list_pending_for_user(self, user_id: int) -> list[UserNotification]:
        return (
            self.db.query(UserNotification)
            .filter(UserNotification.user_id == user_id, UserNotification.is_sent.is_(False))
            .order_by(UserNotification.created_at.asc())
            .all()
        )

    def mark_as_sent(self, notification_id: int) -> None:
        notification = (
            self.db.query(UserNotification)
            .filter(UserNotification.id == notification_id)
            .first()
        )
        if not notification or notification.is_sent:
            return
        notification.is_sent = True
        notification.sent_at = datetime.now(tz=timezone.utc)
        self.db.add(notification)
        self.db.commit()

    def create_notification(
        self,
        *,
        user_id: int,
        title: str,
        description: str,
        notification_type: str | None = None,
        payload: dict[str, Any] | None = None,
        language: str = "ru",
    ) -> UserNotification:
        notification = UserNotification(
            user_id=user_id,
            title=title,
            description=description,
            type=notification_type,
            payload=payload,
            language=language,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification
