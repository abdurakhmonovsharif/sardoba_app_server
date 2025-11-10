from datetime import datetime, timedelta, timezone
import logging
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import OTPCode

from . import exceptions

logger = logging.getLogger(__name__)


class OTPService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _generate_code(self) -> str:
        if self.settings.OTP_STATIC_CODE:
            return self.settings.OTP_STATIC_CODE
        return "".join(secrets.choice("0123456789") for _ in range(self.settings.OTP_LENGTH))

    def request_otp(self, *, phone: str, purpose: str, ip: str | None, user_agent: str | None) -> OTPCode:
        now = datetime.now(tz=timezone.utc)
        window_start = now - timedelta(hours=1)

        phone_count = (
            self.db.query(func.count(OTPCode.id))
            .filter(OTPCode.phone == phone, OTPCode.created_at >= window_start)
            .scalar()
        )
        if phone_count and phone_count >= self.settings.OTP_RATE_LIMIT_PER_HOUR:
            raise exceptions.RateLimitExceeded("OTP request limit reached for this phone")

        if ip:
            ip_count = (
                self.db.query(func.count(OTPCode.id))
                .filter(OTPCode.ip == ip, OTPCode.created_at >= window_start)
                .scalar()
            )
            if ip_count and ip_count >= self.settings.OTP_RATE_LIMIT_PER_HOUR:
                raise exceptions.RateLimitExceeded("OTP request limit reached for this IP")

        code = self._generate_code()
        otp = OTPCode(
            phone=phone,
            code=code,
            purpose=purpose,
            expires_at=now + timedelta(minutes=self.settings.OTP_EXPIRATION_MINUTES),
            ip=ip,
            user_agent=user_agent,
        )
        self.db.add(otp)
        self.db.flush()

        self._send_otp(phone=phone, code=code)
        return otp

    def verify_otp(self, *, phone: str, code: str, purpose: str) -> OTPCode:
        now = datetime.now(tz=timezone.utc)

        otp = (
            self.db.query(OTPCode)
            .filter(
                OTPCode.phone == phone,
                OTPCode.code == code,
                OTPCode.purpose == purpose,
                OTPCode.is_used.is_(False),
            )
            .order_by(OTPCode.created_at.desc())
            .first()
        )
        if not otp:
            if self.settings.OTP_STATIC_CODE and code == self.settings.OTP_STATIC_CODE:
                # Create a synthetic OTP record so downstream logging/token issuance logic still works.
                otp = OTPCode(
                    phone=phone,
                    code=code,
                    purpose=purpose,
                    expires_at=now + timedelta(minutes=self.settings.OTP_EXPIRATION_MINUTES),
                    is_used=True,
                )
                self.db.add(otp)
                self.db.flush()
                return otp
            raise exceptions.OTPInvalid("Invalid OTP code")
        expires_at = otp.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            otp.is_used = True
            self.db.flush()
            raise exceptions.OTPExpired("OTP has expired")

        otp.is_used = True
        self.db.flush()
        return otp

    @staticmethod
    def _send_otp(*, phone: str, code: str) -> None:
        # Dummy implementation - replace with real SMS provider
        logger.info("Sending OTP %s to phone %s", code, phone)
