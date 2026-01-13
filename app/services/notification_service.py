from sqlalchemy.orm import Session

from app.models import Notification, Staff, StaffRole, User, UserNotification

from . import exceptions


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def list_notifications(self, *, page: int, size: int) -> tuple[int, list[Notification]]:
        query = self.db.query(Notification).order_by(Notification.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * size).limit(size).all()
        return total, items

    def create_notification(self, *, actor: Staff, data: dict) -> Notification:
        self._ensure_manager(actor)
        notification = Notification(**data)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        self._fan_out_to_clients(notification)
        return notification

    def get_notification(self, notification_id: int) -> Notification:
        notification = self.db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            raise exceptions.NotFoundError("Notification not found")
        return notification

    def update_notification(self, *, actor: Staff, notification_id: int, data: dict) -> Notification:
        self._ensure_manager(actor)
        notification = self.get_notification(notification_id)
        for field, value in data.items():
            setattr(notification, field, value)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def delete_notification(self, *, actor: Staff, notification_id: int) -> None:
        self._ensure_manager(actor)
        notification = self.get_notification(notification_id)
        self.db.query(UserNotification).filter(
            UserNotification.notification_id == notification_id
        ).delete(synchronize_session=False)
        self.db.delete(notification)
        self.db.commit()

    @staticmethod
    def _ensure_manager(actor: Staff) -> None:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can perform this action")

    def _fan_out_to_clients(self, notification: Notification) -> None:
        """Create per-user notifications for all active users so clients can see them."""
        user_ids = [row[0] for row in self.db.query(User.id).filter(User.is_deleted == False).all()]  # noqa: E712
        if not user_ids:
            return
        records = [
            UserNotification(
                user_id=user_id,
                notification_id=notification.id,
                title=notification.title,
                description=notification.description,
                type=None,
                payload=None,
                language="ru",
            )
            for user_id in user_ids
        ]
        try:
            self.db.bulk_save_objects(records)
            self.db.commit()
        except Exception:
            self.db.rollback()
            # do not raise; broadcast fan-out is best-effort
