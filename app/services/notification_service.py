from sqlalchemy.orm import Session

from app.models import Notification, Staff, StaffRole

from . import exceptions


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def list_notifications(self) -> list[Notification]:
        return self.db.query(Notification).order_by(Notification.created_at.desc()).all()

    def create_notification(self, *, actor: Staff, data: dict) -> Notification:
        self._ensure_manager(actor)
        notification = Notification(**data)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
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
        self.db.delete(notification)
        self.db.commit()

    @staticmethod
    def _ensure_manager(actor: Staff) -> None:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can perform this action")
