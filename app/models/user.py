from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from .base import Base, TimestampMixin
from .enums import UserLevel

if TYPE_CHECKING:  # pragma: no cover
    from .card import Card
    from .cashback import CashbackBalance, CashbackTransaction
    from .notification_token import NotificationDeviceToken
    from .user_notification import UserNotification
    from .staff import Staff


class User(TimestampMixin, Base):
    __tablename__ = "users"
    LEVEL_SEQUENCE: ClassVar[tuple[UserLevel, ...]] = (
        UserLevel.SILVER,
        UserLevel.GOLD,
        UserLevel.PREMIUM,
        UserLevel.VIP,
    )
    LEVEL_THRESHOLDS: ClassVar[dict[UserLevel, Decimal]] = {
        UserLevel.SILVER: Decimal("0"),
        UserLevel.GOLD: Decimal("10000"),
        UserLevel.PREMIUM: Decimal("40000"),
        UserLevel.VIP: Decimal("120000"),
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    surname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"), nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    level: Mapped[UserLevel] = mapped_column(
        Enum(UserLevel, name="user_level"),
        nullable=False,
        default=UserLevel.SILVER,
        server_default=UserLevel.SILVER.value,
    )
    iiko_wallet_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    iiko_customer_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    pending_iiko_profile_update: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    deleted: Mapped[bool] = synonym("is_deleted")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    waiter: Mapped[Optional["Staff"]] = relationship("Staff", back_populates="clients")
    cashback_wallet: Mapped[Optional["CashbackBalance"]] = relationship(
        "CashbackBalance",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    cashback_transactions: Mapped[list["CashbackTransaction"]] = relationship(
        "CashbackTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    cards: Mapped[list["Card"]] = relationship(
        "Card",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notification_tokens: Mapped[list["NotificationDeviceToken"]] = relationship(
        "NotificationDeviceToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notifications: Mapped[list["UserNotification"]] = relationship(
        "UserNotification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def cashback_balance(self) -> Decimal:
        if self.cashback_wallet is None or self.cashback_wallet.balance is None:
            return Decimal("0.00")
        return self.cashback_wallet.balance

    @cashback_balance.setter
    def cashback_balance(self, value: Decimal) -> None:
        if self.cashback_wallet is None:
            from app.models.cashback import CashbackBalance

            self.cashback_wallet = CashbackBalance(balance=value)
        else:
            self.cashback_wallet.balance = value

    @staticmethod
    def _normalize_points(value: Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @classmethod
    def determine_level_for_balance(cls, balance: Decimal | None) -> UserLevel:
        normalized = cls._normalize_points(balance)
        for level in reversed(cls.LEVEL_SEQUENCE):
            threshold = cls.LEVEL_THRESHOLDS.get(level)
            if threshold is not None and normalized >= threshold:
                return level
        return UserLevel.SILVER

    def apply_level_from_points(self, points: Decimal | None) -> bool:
        new_level = self.determine_level_for_balance(points)
        if self.level != new_level:
            self.level = new_level
            return True
        return False

    def apply_level_from_balance(self, balance: Decimal | None) -> bool:
        # Keep compatibility for APIs that still call this method.
        return self.apply_level_from_points(balance)

    @classmethod
    def _next_level(cls, level: UserLevel) -> UserLevel | None:
        try:
            idx = cls.LEVEL_SEQUENCE.index(level)
        except ValueError:
            return None
        if idx + 1 < len(cls.LEVEL_SEQUENCE):
            return cls.LEVEL_SEQUENCE[idx + 1]
        return None

    def loyalty_metrics(self) -> dict[str, Decimal | UserLevel | None]:
        zero = Decimal("0")
        balance = self.cashback_balance or zero
        points_total = (
            self.cashback_wallet.points
            if self.cashback_wallet and self.cashback_wallet.points is not None
            else zero
        )
        current_floor = self.LEVEL_THRESHOLDS.get(self.level, zero)
        next_level = self._next_level(self.level)
        next_threshold = self.LEVEL_THRESHOLDS.get(next_level) if next_level else None
        progress = points_total - current_floor
        if progress < zero:
            progress = zero
        if next_threshold is not None:
            points_to_next = next_threshold - points_total
            if points_to_next < zero:
                points_to_next = zero
            current_cap = next_threshold
        else:
            points_to_next = None
            current_cap = points_total
        return {
            "level": self.level,
            "balance": balance,
            "points": points_total,
            "current_level_floor": current_floor,
            "current_level_cap": current_cap,
            "progress_in_level": progress,
            "next_level": next_level,
            "next_level_threshold": next_threshold,
            "points_to_next": points_to_next,
        }
