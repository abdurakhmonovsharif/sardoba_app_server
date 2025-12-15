import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from .iiko_service import IikoService
from . import exceptions as service_exceptions

logger = logging.getLogger("iiko.profile_sync")


class IikoProfileSyncService:
    COMMENT = "CASHBACK MOBILE APP CLIENT"

    def __init__(self, db: Session):
        self.db = db
        self.iiko_service = IikoService()

    def sync_profile_updates(self, user: User, updates: dict[str, Any] | None) -> None:
        payload = self._compose_payload(user.pending_iiko_profile_update, updates)
        if not payload:
            return
        self._send_payload(user, payload)

    def flush_pending_updates(self, user: User) -> None:
        if not user.pending_iiko_profile_update:
            return
        self._send_payload(user, user.pending_iiko_profile_update)

    def _compose_payload(self, pending: dict[str, Any] | None, updates: dict[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if pending:
            merged.update(pending)
        if updates:
            for key, value in updates.items():
                if value is None:
                    continue
                merged[key] = value
        return merged

    def _send_payload(self, user: User, payload: dict[str, Any]) -> None:
        payload_to_send = dict(payload)
        payload_to_send.setdefault("comment", self.COMMENT)
        try:
            self.iiko_service.create_or_update_customer(phone=user.phone, payload_extra=payload_to_send)
        except service_exceptions.ServiceError as exc:
            logger.warning("Failed to sync profile to Iiko for user %s: %s", user.id, exc)
            user.pending_iiko_profile_update = payload
            self.db.add(user)
            return
        user.pending_iiko_profile_update = None
        self.db.add(user)
