from datetime import date, datetime, timedelta, timezone
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
import httpx
import logging
import secrets
import string
from typing import Any

from app.core.cache import RedisCacheBackend, cache_manager
from app.core.locking import make_lock
from app.core.observability import correlation_context

from jwt import InvalidTokenError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.models import (
    AuthAction,
    AuthActorType,
    AuthLog,
    Staff,
    StaffRole,
    User,
    Card,
    CashbackBalance,
)

from . import exceptions
from .auth_log_service import log_auth_event
from .card_service import CardService
from .iiko_profile_sync_service import IikoProfileSyncService
from .iiko_service import IikoService
from .otp_service import OTPService

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """
    Reports outcome of a sync attempt.
    ok: no fatal error (even if nothing changed)
    updated: at least one field changed
    changed_fields: names of fields that changed
    warnings: non-fatal issues encountered
    error: fatal reason if ok is False
    """

    ok: bool = True
    updated: bool = False
    changed_fields: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    correlation_id: str | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, reason: str) -> "SyncResult":
        self.ok = False
        self.error = reason
        return self

    def add_change(self, field: str) -> None:
        self.changed_fields.add(field)
        self.updated = True

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_operation(self, name: str, status: str, reason: str | None = None) -> None:
        entry = {"operation": name, "status": status}
        if reason:
            entry["reason"] = reason
        self.operations.append(entry)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "updated": self.updated,
            "changed_fields": sorted(self.changed_fields),
            "warnings": self.warnings,
            "error": self.error,
            "operations": self.operations,
            "correlation_id": self.correlation_id,
        }


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.otp_service = OTPService(db)
        self.card_service = CardService(db)
        self.profile_sync_service = IikoProfileSyncService(db)
        self.iiko_service = IikoService()
        self._cache_backend = cache_manager.get_backend()
        self._redis_client = self._cache_backend.client if isinstance(self._cache_backend, RedisCacheBackend) else None

    def issue_tokens(self, *, actor_type: AuthActorType, subject_id: int, extra: dict | None = None) -> dict[str, str]:
        claims = extra.copy() if extra else {}
        claims["actor_type"] = actor_type.value
        access = security.create_access_token(subject=subject_id, token_type=actor_type.value, additional_claims=claims)
        refresh = security.create_refresh_token(subject=subject_id, token_type=actor_type.value, additional_claims=claims)
        return {"access": access, "refresh": refresh}

    def request_client_otp(self, *, phone: str, purpose: str, ip: str | None, user_agent: str | None) -> None:
        normalized_purpose = (purpose or "").lower()
        active_user_exists = (
            self.db.query(User.id)
            .filter(User.phone == phone, User.is_deleted == False)
            .first()
        )
        if normalized_purpose == "register":
            if active_user_exists:
                raise exceptions.ConflictError("Bu telefon raqamda foydalanuvchu mavjud.")
        else:
            if not active_user_exists:
                raise exceptions.NotFoundError("Bu raqam orqali foydalanuvchi yo'q, iltimos akkaunt yaratishni bosing.")
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
        request_payload = {
            "phone": phone,
            "code": code,
            "purpose": purpose,
            "name": name,
            "waiter_referral_code": waiter_referral_code,
            "date_of_birth": date_of_birth.isoformat() if date_of_birth else None,
        }
        logger.info("Verify client OTP request body: %s", request_payload)
        waiter = None
        if waiter_referral_code:
            waiter = (
                self.db.query(Staff)
                .filter(Staff.referral_code == waiter_referral_code, Staff.role == StaffRole.WAITER)
                .first()
            )
            if waiter is None:
                raise exceptions.NotFoundError("Invalid waiter referral code")

        normalized_purpose = (purpose or "").lower()
        is_register = normalized_purpose == "register"
        user = self.db.query(User).filter(User.phone == phone).first()

        if user and user.is_deleted:
            user.is_deleted = False
            user.deleted_at = None
            self.db.add(user)

        if user and not user.is_deleted:
            self._update_user_profile(user, name, date_of_birth, waiter)
        else:
            if not is_register:
                raise exceptions.NotFoundError(
                    "Bu raqam orqali foydalanuvchi topilmadi, iltimos akkaunt yaratishni bosing."
                )
            user = user or User(phone=phone, name=name, date_of_birth=date_of_birth)
            if waiter:
                user.waiter = waiter
            self.db.add(user)
            self.db.flush()
            self._update_user_profile(user, name, date_of_birth, waiter)

        self.db.flush()

        if is_register:
            result = self.sync_user_from_iiko(user, create_if_missing=True, admin_sync=True)
            if not result.ok:
                self.db.rollback()
                raise exceptions.ServiceError(
                    f"Iiko sync failed during registration: {result.error or 'unknown_error'}"
                )
        else:
            if not user.iiko_customer_id:
                self.db.rollback()
                raise exceptions.ConflictError(
                    "Profilingiz iiko bilan bog'lanmagan. Iltimos qayta ro'yxatdan o'ting yoki qo'llab-quvvatlashga murojaat qiling."
                )

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

        # Flush pending profile updates only when we already have a linked iiko customer to avoid background creation.
        if user.iiko_customer_id and self.profile_sync_service:
            self.profile_sync_service.flush_pending_updates(user)

        self.db.commit()
        self.db.refresh(user)
        return user, tokens

    def _find_active_user_by_phone(self, phone: str) -> User | None:
        return (
            self.db.query(User)
            .filter(User.phone == phone, User.is_deleted == False)
            .first()
        )

    def _update_user_profile(
        self,
        user: User,
        name: str | None,
        date_of_birth: date | None,
        waiter: Staff | None,
    ) -> None:
        updated = False
        if name and user.name != name:
            user.name = name
            updated = True
        if date_of_birth and user.date_of_birth != date_of_birth:
            user.date_of_birth = date_of_birth
            updated = True
        if waiter and not user.waiter_id:
            user.waiter = waiter
            updated = True
        if updated:
            self.db.add(user)

    def _sync_user_with_iiko(self, user: User, payload: dict[str, Any], *, admin_sync: bool = False) -> tuple[bool, str | None]:
        if not payload:
            return False, "empty_payload"
        customer_id = payload.get("id") or payload.get("customerId")
        if customer_id:
            user.iiko_customer_id = customer_id
        wallet_id = self._extract_wallet_id(payload)
        if wallet_id:
            self._assign_wallet_to_user(user, wallet_id)
        self._assign_iiko_name_parts(user, payload)
        iiko_name = self._compose_iiko_name(payload)
        if iiko_name and not user.name:
            user.name = iiko_name
        birthday = self._parse_iiko_birthday(payload.get("birthday"))
        if birthday and not user.date_of_birth:
            user.date_of_birth = birthday
        gender = self._map_iiko_sex(payload.get("sex") or payload.get("gender"))
        if gender and not user.gender:
            user.gender = gender
        if not user.email and payload.get("email"):
            user.email = payload.get("email")
        cashback_changed, cashback_issue = self._sync_cashback_from_wallets(
            user,
            payload.get("walletBalances") or [],
            admin_sync=admin_sync,
        )
        for card_payload in payload.get("cards") or []:
            self.card_service.ensure_card_from_iiko(user, card_payload)
        self.db.add(user)
        return cashback_changed, cashback_issue

    def _sync_cashback_from_wallets(
        self,
        user: User,
        wallets: list[dict[str, Any]],
        *,
        admin_sync: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Returns (changed, issue)
        issue is a short code when cashback could not be refreshed.
        """
        if not wallets:
            logger.warning("Iiko walletBalances empty for %s", user.phone)
            return False, "wallets_empty"

        target_wallet = next((w for w in wallets if w.get("type") == 1), wallets[0])
        balance_value = next(
            (target_wallet.get(key) for key in ("balance", "availableBalance", "amount") if target_wallet.get(key) is not None),
            None,
        )
        if balance_value is None:
            logger.warning(
                "Iiko cashback balance missing for %s wallet=%s",
                user.phone,
                target_wallet.get("id") or target_wallet.get("walletId"),
            )
            return False, "balance_missing"

        try:
            balance_decimal = Decimal(str(balance_value))
        except Exception:
            logger.warning(
                "Failed to parse Iiko cashback balance %s for %s",
                balance_value,
                user.phone,
                exc_info=True,
            )
            return False, "balance_parse_error"

        zero = Decimal("0")
        existing = user.cashback_wallet.balance if user.cashback_wallet else None
        if user.cashback_wallet is None:
            user.cashback_wallet = CashbackBalance(
                user_id=user.id,
                balance=balance_decimal,
                points=zero,
            )
        else:
            user.cashback_wallet.balance = balance_decimal
            user.cashback_wallet.points = user.cashback_wallet.points or zero

        self.db.add(user.cashback_wallet)
        changed = existing is None or balance_decimal != existing
        return changed, None

    def sync_user_from_iiko(
        self,
        user: User,
        *,
        create_if_missing: bool = False,
        max_create_attempts: int = 2,
        create_retry_delay: float = 1.0,
        admin_sync: bool = False,
    ) -> SyncResult:
        sync_corr = f"iiko-sync-{uuid.uuid4().hex[:12]}"
        result = SyncResult(correlation_id=sync_corr)

        def _do_sync() -> SyncResult:
            with correlation_context(sync_corr):
                logger.info(
                    "iiko_sync_start",
                    extra={"user_id": user.id, "phone": user.phone, "admin_sync": admin_sync},
                )
                result.add_operation("sync_start", "attempted")

                if not user.phone:
                    logger.warning("sync_abort_missing_phone", extra={"user_id": user.id})
                    result.add_operation("validate_phone", "failed", "missing_phone")
                    return result.fail("missing_phone")

                if user.is_deleted:
                    logger.warning("sync_abort_user_deleted", extra={"user_id": user.id})
                    result.add_operation("validate_user", "failed", "user_deleted")
                    return result.fail("user_deleted")

                result.add_operation("fetch_customer", "attempted")
                try:
                    customer = self._fetch_iiko_customer(user.phone)
                    customer = self._reactivate_iiko_customer_if_deleted(user.phone, customer)
                except exceptions.ServiceError as exc:
                    reason = "lock_contention" if "lock" in str(exc).lower() else "service_error"
                    result.add_operation("fetch_customer", "failed", reason)
                    logger.warning(
                        "fetch_customer_failed",
                        extra={"phone": user.phone, "error": str(exc)},
                    )
                    return result.fail(reason)
                if customer:
                    result.add_operation("fetch_customer", "success")

                if not customer:
                    if not create_if_missing:
                        logger.warning("iiko_customer_not_found", extra={"phone": user.phone})
                        result.add_operation("fetch_customer", "failed", "not_found")
                        return result.fail("iiko_customer_not_found")
                    attempts = max(1, max_create_attempts)
                    for attempt in range(attempts):
                        result.add_operation("create_customer", "attempted", f"attempt_{attempt+1}")
                        created = self._ensure_iiko_customer_safe(
                            user,
                            name=user.name,
                            date_of_birth=user.date_of_birth,
                        )
                        if created:
                            customer = self._fetch_iiko_customer(user.phone) or created
                        if customer:
                            result.add_operation("create_customer", "success", f"attempt_{attempt+1}")
                            break
                        if attempt + 1 < attempts and create_retry_delay > 0:
                            time.sleep(create_retry_delay)
                    if not customer:
                        logger.warning(
                            "iiko_customer_create_failed", extra={"phone": user.phone, "attempts": attempts}
                        )
                        result.add_operation("create_customer", "failed", "max_attempts_reached")
                        return result.fail("iiko_customer_create_failed")

                # Snapshot before syncing to report changes
                previous_customer_id = user.iiko_customer_id
                previous_wallet_id = user.iiko_wallet_id
                previous_cashback = user.cashback_wallet.balance if user.cashback_wallet else None

                result.add_operation("sync_wallets", "attempted")
                cashback_changed, cashback_issue = self._sync_user_with_iiko(user, customer, admin_sync=admin_sync)

                # In admin mode, try one more fetch if cashback couldn't be refreshed (iiko sometimes returns cached/partial wallets)
                if admin_sync and cashback_issue:
                    refreshed_customer = self._fetch_iiko_customer(user.phone)
                    refreshed_customer = self._reactivate_iiko_customer_if_deleted(user.phone, refreshed_customer)
                    if refreshed_customer:
                        refreshed_wallets = refreshed_customer.get("walletBalances") or []
                        refreshed_wallet_id = self._extract_wallet_id(refreshed_customer)
                        if refreshed_wallet_id:
                            self._assign_wallet_to_user(user, refreshed_wallet_id)
                        cashback_changed_retry, cashback_issue_retry = self._sync_cashback_from_wallets(
                            user,
                            refreshed_wallets,
                            admin_sync=True,
                        )
                        if cashback_changed_retry:
                            cashback_changed = True
                            cashback_issue = None
                        else:
                            cashback_issue = cashback_issue_retry or cashback_issue

                if cashback_changed:
                    result.add_change("cashback_balance")
                    result.add_operation("sync_wallets", "success")
                elif cashback_issue and admin_sync:
                    result.add_operation("sync_wallets", "failed", cashback_issue)
                    return result.fail(f"cashback_not_refreshed:{cashback_issue}")
                elif cashback_issue:
                    result.add_operation("sync_wallets", "warning", cashback_issue)
                    result.add_warning(f"cashback_sync_issue:{cashback_issue}")
                else:
                    result.add_operation("sync_wallets", "success")

                card_created = self._ensure_card_exists(user)
                if card_created:
                    result.add_change("card")
                    result.add_operation("ensure_card", "success")
                else:
                    result.add_operation("ensure_card", "skipped", "exists")

                if user.iiko_wallet_id and user.iiko_wallet_id != previous_wallet_id:
                    result.add_change("iiko_wallet_id")
                if user.iiko_customer_id and user.iiko_customer_id != previous_customer_id:
                    result.add_change("iiko_customer_id")

                # Evaluate cashback change again if not captured due to missing walletBalances
                if previous_cashback is not None and user.cashback_wallet:
                    if user.cashback_wallet.balance != previous_cashback:
                        result.add_change("cashback_balance")

                self.db.flush()
                logger.info(
                    "iiko_sync_complete",
                    extra={
                        "user_id": user.id,
                        "phone": user.phone,
                        "status": "SUCCESS" if result.ok else "FAILED",
                        "updated": result.updated,
                        "changed_fields": sorted(result.changed_fields),
                    },
                )
                return result

        if admin_sync:
            admin_lock = make_lock(
                IikoService.ADMIN_LOCK_KEY,
                redis_client=self._redis_client,
                ttl_seconds=IikoService.ADMIN_LOCK_TTL_SECONDS,
                wait_timeout=8,
                retry_interval=0.1,
                log=logger,
            )
            with admin_lock.hold() as acquired:
                if not acquired:
                    logger.warning(
                        "admin_sync_skipped_due_to_lock", extra={"user_id": user.id, "phone": user.phone}
                    )
                    result.add_operation("admin_sync_lock", "failed", "lock_busy")
                    return result.fail("admin_sync_lock_busy")
                result.add_operation("admin_sync_lock", "acquired")
                return _do_sync()

        return _do_sync()

    def _assign_wallet_to_user(self, user: User, wallet_id: str) -> None:
        conflict = (
            self.db.query(User)
            .filter(User.iiko_wallet_id == wallet_id, User.id != user.id)
            .first()
        )
        if conflict:
            conflict.iiko_wallet_id = None
            self.db.add(conflict)
            # flush the conflict update before assigning the wallet to avoid unique constraint races
            self.db.flush()
        user.iiko_wallet_id = wallet_id

    def _extract_wallet_id(self, payload: dict[str, Any]) -> str | None:
        for wallet in payload.get("walletBalances", []) or []:
            wallet_id = wallet.get("id") or wallet.get("walletId")
            if wallet_id:
                return wallet_id
        return None

    def _compose_iiko_name(self, payload: dict[str, Any]) -> str | None:
        if not payload:
            return None
        candidates = []
        for key in ("name", "middleName", "surname"):
            value = payload.get(key)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    candidates.append(cleaned)
        if not candidates:
            full_name = payload.get("fullName") or payload.get("full_name")
            if isinstance(full_name, str):
                cleaned = full_name.strip()
                if cleaned:
                    return cleaned
            return None
        return " ".join(candidates)

    def _assign_iiko_name_parts(self, user: User, payload: dict[str, Any]) -> None:
        if not payload:
            return
        middle_name = self._extract_iiko_string(payload, "middleName", "middle_name")
        surname = self._extract_iiko_string(payload, "surname", "lastName", "familyName")
        if middle_name and not user.middle_name:
            user.middle_name = middle_name
        if surname and not user.surname:
            user.surname = surname

    def _extract_iiko_string(self, payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return None

    def _parse_iiko_birthday(self, value: Any) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(cleaned, fmt).date()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(cleaned).date()
            except ValueError:
                return None
        return None

    def _map_iiko_sex(self, value: Any) -> str | None:
        if value is None:
            return None
        candidate = str(value).strip().lower()
        if not candidate:
            return None
        if candidate in {"1", "male", "m", "man"}:
            return "male"
        if candidate in {"2", "female", "f", "woman"}:
            return "female"
        return candidate

    def _ensure_iiko_customer(self, user: User, *, name: str | None, date_of_birth: date | None) -> dict[str, Any]:
        payload = self._build_customer_payload(user, name=name, date_of_birth=date_of_birth)
        response = self.iiko_service.create_or_update_customer(phone=user.phone, payload_extra=payload)
        self._sync_user_with_iiko(user, response)
        if not user.cards:
            self._bind_card_to_user(user)
        return response

    def _ensure_iiko_customer_safe(self, user: User, *, name: str | None, date_of_birth: date | None) -> dict[str, Any] | None:
        try:
            response = self._ensure_iiko_customer(user, name=name, date_of_birth=date_of_birth)
        except exceptions.ServiceError as exc:
            cause = getattr(exc, "__cause__", None)
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 400:
                raise exceptions.ExternalServiceBadRequest(
                    "Iiko customer creation rejected with Bad Request"
                ) from exc
            logger.warning("Failed to ensure Iiko customer for %s: %s", user.phone, exc)
            return None
        else:
            self._ensure_card_exists(user)
            return response

    def _fetch_iiko_customer(self, phone: str) -> dict[str, Any] | None:
        try:
            return self.iiko_service.get_customer_by_phone(phone)
        except exceptions.ServiceError as exc:
            logger.warning("Unable to lookup Iiko customer %s: %s", phone, exc)
            return None

    def _is_iiko_deleted(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            cleaned = value.strip().lower()
            return cleaned in {"true", "1", "yes", "y"}
        return False

    def _reactivate_iiko_customer_if_deleted(self, phone: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not payload or not self._is_iiko_deleted(payload.get("isDeleted")):
            return payload
        logger.info("Reactivating Iiko customer %s because payload reported deletion", phone)
        try:
            self.iiko_service.create_or_update_customer(
                phone=phone,
                payload_extra={"isDeleted": False},
            )
        except exceptions.ServiceError as exc:
            logger.warning("Failed to reactivate Iiko customer %s: %s", phone, exc)
            return payload
        refreshed = self._fetch_iiko_customer(phone)
        return refreshed or payload

    def _build_customer_payload(self, user: User, *, name: str | None, date_of_birth: date | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"comment": "CASHBACK MOBILE APP CLIENT"}
        cleaned_name = self._clean_value(name or user.name)
        if cleaned_name:
            payload["fullName"] = cleaned_name
            payload["name"] = cleaned_name
        formatted_birthday = self._format_iiko_birthday_value(date_of_birth or user.date_of_birth)
        if formatted_birthday:
            payload["birthday"] = formatted_birthday
        if user.email:
            payload["email"] = user.email
        if user.gender:
            payload["sex"] = user.gender
        surname = self._clean_value(user.surname)
        if surname:
            payload["surname"] = surname
        middle_name = self._clean_value(user.middle_name)
        if middle_name:
            payload["middleName"] = middle_name
        return payload

    def _clean_value(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned if cleaned else None

    def _format_iiko_birthday_value(self, value: date | None) -> str | None:
        if value is None:
            return None
        return f"{value.strftime('%Y-%m-%d')}T00:00:00.000"

    def _bind_card_to_user(self, user: User) -> None:
        if not user.iiko_customer_id:
            raise exceptions.ServiceError("Unable to attach card without iiko customer id")
        card = self.card_service.create_card_for_user(user)
        card_response = self.iiko_service.add_card(
            customer_id=user.iiko_customer_id, card_number=card.card_number, card_track=card.card_track
        )
        iiko_card_id = card_response.get("id") or card_response.get("cardId")
        if iiko_card_id:
            card.iiko_card_id = iiko_card_id
        self.db.add(card)
        self.db.flush()

    def _ensure_card_exists(self, user: User) -> bool:
        if not user.iiko_customer_id:
            return False
        card_exists = (
            self.db.query(Card.id)
            .filter(Card.user_id == user.id)
            .first()
        )
        if card_exists:
            return False
        try:
            self._bind_card_to_user(user)
        except exceptions.ServiceError as exc:
            logger.warning("Failed to ensure card for user %s: %s", user.phone, exc)
            return False
        return True

    def _ensure_user_for_login(self, phone: str) -> User | None:
        user = self._find_active_user_by_phone(phone)
        if user:
            return user
        iiko_customer = self._fetch_iiko_customer(phone)
        iiko_customer = self._reactivate_iiko_customer_if_deleted(phone, iiko_customer)
        if not iiko_customer:
            return None
        user = User(phone=phone, name=iiko_customer.get("fullName"))
        self.db.add(user)
        self.db.flush()
        self._sync_user_with_iiko(user, iiko_customer)
        return user

    def _find_or_create_user_from_iiko(self, phone: str) -> User | None:
        user = self.db.query(User).filter(User.phone == phone).first()
        if user:
            return user
        iiko_customer = self._fetch_iiko_customer(phone)
        iiko_customer = self._reactivate_iiko_customer_if_deleted(phone, iiko_customer)
        if not iiko_customer:
            return None
        user = User(phone=phone, name=iiko_customer.get("fullName"))
        self.db.add(user)
        self.db.flush()
        self._sync_user_with_iiko(user, iiko_customer)
        return user

    def create_staff(
        self,
        *,
        name: str,
        phone: str,
        password: str,
        role: StaffRole,
        branch_id: int | None,
        actor: Staff,
        referral_code: str | None = None,
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
            normalized_referral = referral_code.strip() if referral_code and referral_code.strip() else None
            if normalized_referral:
                exists = (
                    self.db.query(func.count(Staff.id))
                    .filter(Staff.referral_code == normalized_referral)
                    .scalar()
                )
                if exists:
                    raise exceptions.ConflictError("Waiter with this referral code already exists")
                staff.referral_code = normalized_referral
            else:
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
        self._ensure_login_rate_limit(ip=ip)
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
        if payload.get("mock_user"):
            extra = {k: v for k, v in payload.items() if k not in {"sub", "exp", "scope", "type", "actor_type"}}
            return self.issue_tokens(actor_type=AuthActorType(actor_type), subject_id=subject_id, extra=extra)
        if actor_type == AuthActorType.CLIENT.value:
            if not self.db.query(User.id).filter(User.id == subject_id).first():
                raise exceptions.AuthenticationError("User not found")
        else:
            if not self.db.query(Staff.id).filter(Staff.id == subject_id).first():
                raise exceptions.AuthenticationError("Staff not found")
        extra = {k: v for k, v in payload.items() if k not in {"sub", "exp", "scope", "type", "actor_type"}}
        tokens = self.issue_tokens(actor_type=AuthActorType(actor_type), subject_id=subject_id, extra=extra)
        return tokens

    def _ensure_login_rate_limit(self, *, ip: str | None) -> None:
        if not ip:
            return
        threshold = self.settings.LOGIN_RATE_LIMIT_PER_WINDOW
        if not threshold:
            return
        window_start = datetime.now(tz=timezone.utc) - timedelta(minutes=self.settings.RATE_LIMIT_BLOCK_MINUTES)
        recent_failures = (
            self.db.query(func.count(AuthLog.id))
            .filter(
                AuthLog.ip == ip,
                AuthLog.action == AuthAction.FAILED_LOGIN,
                AuthLog.created_at >= window_start,
            )
            .scalar()
        )
        if recent_failures and recent_failures >= threshold:
            raise exceptions.RateLimitExceeded(self._rate_limit_block_message())

    def _generate_referral_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            referral_code = "".join(secrets.choice(alphabet) for _ in range(6))
            exists = self.db.query(func.count(Staff.id)).filter(Staff.referral_code == referral_code).scalar()
            if not exists:
                return referral_code
        raise exceptions.ServiceError("Failed to generate unique referral code")

    def _rate_limit_block_message(self) -> str:
        return f"Ko'p so'rov jonatildi, {self.settings.RATE_LIMIT_BLOCK_MINUTES} daqiqadan keyin yana urinib ko'ring."
