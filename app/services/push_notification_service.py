import logging
from concurrent.futures import Future
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.db import session_scope
from app.core.notification_ws import notification_ws_manager
from app.models import UserNotification
from app.services.notification_token_service import NotificationTokenService
from app.services.user_notification_service import UserNotificationService

logger = logging.getLogger("push.service")

MESSAGE_TEMPLATES = {
    "uz": {
        "accrual": ("Cashback qo‘shildi", "+{amount} so‘m hisobingizga cashback qo‘shildi!"),
        "spent": ("Cashback ishlatildi", "-{amount} so‘m cashbackdan ishlatildi"),
    },
    "ru": {
        "accrual": ("Кешбек начислен", "+{amount} сум начислено на ваш кешбек!"),
        "spent": ("Кешбек использован", "-{amount} сум списано с кешбека"),
    },
}


def build_cashback_message(language: str, amount_str: str, amount: Decimal) -> tuple[str, str]:
    key = "accrual" if amount > 0 else "spent"
    localized = MESSAGE_TEMPLATES.get(language, MESSAGE_TEMPLATES["ru"])
    title_template, body_template = localized[key]
    return title_template, body_template.format(amount=amount_str)


def _mark_notification_as_sent(notification_id: int) -> None:
    with session_scope() as session:
        notification = (
            session.query(UserNotification).filter(UserNotification.id == notification_id).first()
        )
        if not notification or notification.is_sent:
            return
        notification.is_sent = True
        notification.sent_at = datetime.now(tz=timezone.utc)
        session.add(notification)


def _on_ws_send_done(notification_id: int, fut: Future[bool]) -> None:
    try:
        success = fut.result()
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        logger.debug("Websocket delivery failed for %s: %s", notification_id, exc)
        success = False
    if success:
        _mark_notification_as_sent(notification_id)


class PushNotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.token_service = NotificationTokenService(db)
        self.notification_service = UserNotificationService(db)

    def notify_cashback_change(self, user_id: int, amount: Decimal) -> None:
        if amount == 0:
            return
        data_type = "cashback_accrual" if amount > 0 else "cashback_spent"
        amount_str = str(abs(amount))
        language = self._preferred_language_for_user(user_id)
        title, description = build_cashback_message(language, amount_str, amount)
        payload = {"type": data_type, "amount": str(amount)}
        try:
            notification = self.notification_service.create_notification(
                user_id=user_id,
                title=title,
                description=description,
                notification_type=data_type,
                payload=payload,
                language=language,
            )
        except Exception as exc:
            logger.warning("Failed to persist notification for user %s: %s", user_id, exc)
            return
        self._dispatch_notification(notification, payload)

    def send_admin_notification(
        self,
        user_id: int,
        title: str,
        description: str,
        notification_type: str | None = None,
        payload: dict[str, str] | None = None,
        language: str = "ru",
    ) -> None:
        try:
            notification = self.notification_service.create_notification(
                user_id=user_id,
                title=title,
                description=description,
                notification_type=notification_type,
                payload=payload,
                language=language,
            )
        except Exception as exc:
            logger.warning("Failed to persist admin notification for user %s: %s", user_id, exc)
            return
        self._dispatch_notification(notification, payload or {})

    def _preferred_language_for_user(self, user_id: int) -> str:
        tokens = self.token_service.tokens_for_user(user_id)
        for token in tokens:
            if token.language:
                return token.language
        return "ru"

    def _dispatch_notification(self, notification: UserNotification, payload: dict) -> None:
        message_payload = payload or notification.payload or {}
        message = {
            "notification_id": notification.id,
            "title": notification.title,
            "description": notification.description,
            "payload": message_payload,
            "language": notification.language,
            "type": notification.type,
        }
        future = notification_ws_manager.schedule_send(notification.user_id, message)
        if future is not None:
            future.add_done_callback(lambda fut: _on_ws_send_done(notification.id, fut))
