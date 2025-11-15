from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(slots=True)
class SMSMessageResult:
    """Normalized response returned by SMS providers."""

    phone: str
    message: str
    provider: str
    provider_message_id: Optional[str] = None
    provider_status: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class BaseSMSProvider(ABC):
    """Interface all SMS providers must implement."""

    name: str

    @abstractmethod
    def send_text(self, *, phone: str, message: str) -> SMSMessageResult:
        """Send the given text to the phone number."""
        raise NotImplementedError
