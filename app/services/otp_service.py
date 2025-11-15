from datetime import datetime, timedelta, timezone
import logging
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import OTPCode
from app.services.sms_providers import EskizSMSProvider

from . import exceptions

logger = logging.getLogger(__name__)


class OTPService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.sms_logger = logging.getLogger("app.sms")
        self._rate_limit_bypass = {
            self._normalize_phone(phone) for phone in self.settings.OTP_RATE_LIMIT_BYPASS_PHONES
        }
        self._sms_provider: EskizSMSProvider | None = None
        if not self.settings.SMS_DRY_RUN:
            self._sms_provider = EskizSMSProvider(
                email=self.settings.ESKIZ_LOGIN,
                password=self.settings.ESKIZ_PASSWORD,
                sender=self.settings.ESKIZ_FROM_WHOM,
            )

    def _generate_code(self) -> str:
        if self.settings.OTP_STATIC_CODE:
            return self.settings.OTP_STATIC_CODE
        return "".join(secrets.choice("0123456789") for _ in range(self.settings.OTP_LENGTH))

    def request_otp(self, *, phone: str, purpose: str, ip: str | None, user_agent: str | None) -> OTPCode:
        now = datetime.now(tz=timezone.utc)
        normalized_phone = self._normalize_phone(phone)
        window_start = now - timedelta(hours=1)

        skip_rate_limit = normalized_phone in self._rate_limit_bypass

        if not skip_rate_limit:
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
        else:
            logger.debug("Rate limit bypassed for phone %s", phone)

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

    def _send_otp(self, *, phone: str, code: str) -> None:
        message = self.settings.ESKIZ_SMS_TEMPLATE.format(code=code)

        if self.settings.SMS_DRY_RUN:
            self.sms_logger.info(
                "DRY-RUN OTP SMS | phone=%s | code=%s | message=\"%s\"",
                phone,
                code,
                message,
            )
            return

        if not self._sms_provider:
            raise exceptions.OTPDeliveryFailed("SMS provider is not configured")

        try:
            result = self._sms_provider.send_text(phone=phone, message=message)
        except exceptions.SMSDeliveryError as exc:
            raise exceptions.OTPDeliveryFailed("Failed to deliver OTP SMS") from exc

        self.sms_logger.info(
            "OTP SMS sent | phone=%s | code=%s | message=\"%s\" | provider=%s | status=%s | provider_message_id=%s",
            phone,
            code,
            message,
            result.provider,
            result.provider_status,
            result.provider_message_id,
        )
        if result.meta:
            self.sms_logger.debug("OTP SMS response meta | phone=%s | meta=%s", phone, result.meta)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return phone.strip().replace(" ", "")
