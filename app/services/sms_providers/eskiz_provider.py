from __future__ import annotations

import logging
from typing import Any

from eskiz_sms import EskizSMS
from eskiz_sms.exceptions import EskizException

from ..exceptions import SMSDeliveryError
from .base import BaseSMSProvider, SMSMessageResult

logger = logging.getLogger(__name__)


class EskizSMSProvider(BaseSMSProvider):
    """Eskiz implementation of the SMS provider interface."""

    name = "eskiz"

    def __init__(self, *, email: str, password: str, sender: str, callback_url: str | None = None):
        self._sender = sender
        self._client = EskizSMS(email=email, password=password, callback_url=callback_url)

    def send_text(self, *, phone: str, message: str) -> SMSMessageResult:
        logger.debug("Sending Eskiz SMS | phone=%s", phone)
        try:
            response = self._client.send_sms(
                mobile_phone=phone,
                message=message,
                from_whom=self._sender,
            )
        except EskizException as exc:
            logger.exception("Eskiz SMS sending failed | phone=%s", phone)
            raise SMSDeliveryError(f"Eskiz rejected SMS send request: {exc}") from exc

        meta: dict[str, Any] = {}
        if response.message:
            meta["message"] = response.message
        if response.data:
            meta["data"] = response.data

        return SMSMessageResult(
            phone=phone,
            message=message,
            provider=self.name,
            provider_message_id=response.id,
            provider_status=response.status,
            meta=meta or None,
        )
