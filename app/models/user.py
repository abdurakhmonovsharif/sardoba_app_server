from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import ClassVar, Optional, TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import UserLevel

if TYPE_CHECKING:  # pragma: no cover
    from .cashback import CashbackBalance, CashbackTransaction
    from .staff import Staff


class User(TimestampMixin, Base):
    __tablename__ = "users"
    LEVEL_SEQUENCE: ClassVar[tuple[UserLevel, ...]] = (
        UserLevel.SILVER,
        UserLevel.GOLD,
        UserLevel.PREMIUM,
    )
    LEVEL_THRESHOLDS: ClassVar[dict[UserLevel, Decimal]] = {
        UserLevel.SILVER: Decimal("0"),
        UserLevel.GOLD: Decimal("1000"),
        UserLevel.PREMIUM: Decimal("3000"),
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    level: Mapped[UserLevel] = mapped_column(
        Enum(UserLevel, name="user_level"),
        nullable=False,
        default=UserLevel.SILVER,
        server_default=UserLevel.SILVER.value,
    )

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
        self.apply_level_from_balance(value)

    @staticmethod
    def determine_level_for_balance(balance: Decimal | None) -> UserLevel:
        if balance is None:
            normalized = Decimal("0")
        elif isinstance(balance, Decimal):
            normalized = balance
        else:
            normalized = Decimal(str(balance))
        if normalized >= Decimal("3000"):
            return UserLevel.PREMIUM
        if normalized >= Decimal("1000"):
            return UserLevel.GOLD
        return UserLevel.SILVER

    def apply_level_from_balance(self, balance: Decimal | None) -> bool:
        new_level = self.determine_level_for_balance(balance)
        if self.level != new_level:
            self.level = new_level
            return True
        return False

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
        current_floor = self.LEVEL_THRESHOLDS.get(self.level, zero)
        next_level = self._next_level(self.level)
        next_threshold = self.LEVEL_THRESHOLDS.get(next_level) if next_level else None
        progress = balance - current_floor
        if progress < zero:
            progress = zero
        if next_threshold is not None:
            points_to_next = next_threshold - balance
            if points_to_next < zero:
                points_to_next = zero
            current_cap = next_threshold
        else:
            points_to_next = None
            current_cap = balance
        return {
            "level": self.level,
            "balance": balance,
            "current_level_floor": current_floor,
            "current_level_cap": current_cap,
            "progress_in_level": progress,
            "next_level": next_level,
            "next_level_threshold": next_threshold,
            "points_to_next": points_to_next,
        }
