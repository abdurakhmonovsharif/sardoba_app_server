from datetime import date, datetime, timezone
import logging
import secrets
import string

from jwt import InvalidTokenError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.models import (
    AuthAction,
    AuthActorType,
    Staff,
    StaffRole,
    User,
)

from . import exceptions
from .auth_log_service import log_auth_event
from .otp_service import OTPService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.otp_service = OTPService(db)

    def issue_tokens(self, *, actor_type: AuthActorType, subject_id: int, extra: dict | None = None) -> dict[str, str]:
        claims = extra.copy() if extra else {}
        claims["actor_type"] = actor_type.value
        access = security.create_access_token(subject=subject_id, token_type=actor_type.value, additional_claims=claims)
        refresh = security.create_refresh_token(subject=subject_id, token_type=actor_type.value, additional_claims=claims)
        return {"access": access, "refresh": refresh}

    def request_client_otp(self, *, phone: str, purpose: str, ip: str | None, user_agent: str | None) -> None:
        otp = self.otp_service.request_otp(phone=phone, purpose=purpose, ip=ip, user_agent=user_agent)
        log_auth_event(
            db=self.db,
            actor_type=AuthActorType.CLIENT,
            action=AuthAction.OTP_REQUEST,
            phone=phone,
            ip=ip,
            user_agent=user_agent,
            meta={"purpose": purpose, "otp_id": otp.id},
        )
        self.db.commit()

    def verify_client_otp(
        self,
        *,
        phone: str,
        code: str,
        purpose: str,
        name: str | None,
        waiter_referral_code: str | None,
        date_of_birth: date | None,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[User, dict[str, str]]:
        otp = self.otp_service.verify_otp(phone=phone, code=code, purpose=purpose)

        waiter = None
        if waiter_referral_code:
            waiter = (
                self.db.query(Staff)
                .filter(Staff.referral_code == waiter_referral_code, Staff.role == StaffRole.WAITER)
                .first()
            )
            if waiter is None:
                raise exceptions.NotFoundError("Invalid waiter referral code")

        user = self.db.query(User).filter(User.phone == phone).first()
        if not user:
            if (purpose or "").lower() != "register":
                raise exceptions.NotFoundError("User not found. Please register first.")
            user = User(phone=phone, name=name, date_of_birth=date_of_birth)
            if waiter:
                user.waiter = waiter
            self.db.add(user)
        else:
            if name:
                user.name = name
            if waiter and not user.waiter_id:
                user.waiter = waiter
            if date_of_birth:
                user.date_of_birth = date_of_birth

        self.db.flush()

        tokens = self.issue_tokens(actor_type=AuthActorType.CLIENT, subject_id=user.id)

        log_auth_event(
            db=self.db,
            actor_type=AuthActorType.CLIENT,
            action=AuthAction.OTP_VERIFICATION,
            actor_id=user.id,
            phone=phone,
            ip=ip,
            user_agent=user_agent,
            meta={"purpose": purpose, "otp_id": otp.id},
        )
        self.db.commit()
        self.db.refresh(user)
        return user, tokens

    def create_staff(
        self,
        *,
        name: str,
        phone: str,
        password: str,
        role: StaffRole,
        branch_id: int | None,
        actor: Staff,
    ) -> Staff:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can create staff")

        password_hash = security.create_password_hash(password)
        staff = Staff(
            name=name,
            phone=phone,
            password_hash=password_hash,
            role=role,
            branch_id=branch_id,
        )
        if role == StaffRole.WAITER:
            staff.referral_code = self._generate_referral_code()

        self.db.add(staff)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise exceptions.ConflictError("Staff with this phone already exists") from exc

        self.db.refresh(staff)
        return staff

    def staff_login(self, *, phone: str, password: str, ip: str | None, user_agent: str | None) -> tuple[Staff, dict[str, str]]:
        identifier = phone.strip()
        staff = self.db.query(Staff).filter(Staff.phone == identifier).first()
        if not staff or not security.verify_password(password, staff.password_hash):
            log_auth_event(
                db=self.db,
                actor_type=AuthActorType.STAFF,
                action=AuthAction.FAILED_LOGIN,
                phone=phone,
                ip=ip,
                user_agent=user_agent,
            )
            self.db.commit()
            raise exceptions.AuthenticationError("Invalid credentials")

        tokens = self.issue_tokens(
            actor_type=AuthActorType.STAFF,
            subject_id=staff.id,
            extra={"role": staff.role.value},
        )

        log_auth_event(
            db=self.db,
            actor_type=AuthActorType.STAFF,
            action=AuthAction.LOGIN,
            actor_id=staff.id,
            phone=phone,
            ip=ip,
            user_agent=user_agent,
        )
        self.db.commit()
        return staff, tokens

    def change_staff_password(self, *, staff: Staff, old_password: str, new_password: str) -> None:
        if not security.verify_password(old_password, staff.password_hash):
            raise exceptions.AuthenticationError("Old password is incorrect")
        staff.password_hash = security.create_password_hash(new_password)
        staff.updated_at = datetime.now(tz=timezone.utc)
        self.db.add(staff)
        self.db.commit()

    def refresh_tokens(self, *, refresh_token: str) -> dict[str, str]:
        try:
            payload = security.decode_refresh_token(refresh_token)
        except InvalidTokenError as exc:
            raise exceptions.AuthenticationError("Invalid refresh token") from exc
        if payload.get("scope") != "refresh":
            raise exceptions.AuthenticationError("Invalid refresh token")

        actor_type = payload.get("actor_type")
        if actor_type not in {AuthActorType.CLIENT.value, AuthActorType.STAFF.value}:
            raise exceptions.AuthenticationError("Invalid token actor type")

        subject_id = int(payload["sub"])
        if actor_type == AuthActorType.CLIENT.value:
            if not self.db.query(User.id).filter(User.id == subject_id).first():
                raise exceptions.AuthenticationError("User not found")
        else:
            if not self.db.query(Staff.id).filter(Staff.id == subject_id).first():
                raise exceptions.AuthenticationError("Staff not found")
        extra = {k: v for k, v in payload.items() if k not in {"sub", "exp", "scope", "type", "actor_type"}}
        tokens = self.issue_tokens(actor_type=AuthActorType(actor_type), subject_id=subject_id, extra=extra)
        return tokens

    def _generate_referral_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            referral_code = "".join(secrets.choice(alphabet) for _ in range(6))
            exists = self.db.query(func.count(Staff.id)).filter(Staff.referral_code == referral_code).scalar()
            if not exists:
                return referral_code
        raise exceptions.ServiceError("Failed to generate unique referral code")
