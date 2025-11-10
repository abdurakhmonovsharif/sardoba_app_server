from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DECIMAL, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import CashbackSource

if TYPE_CHECKING:  # pragma: no cover
    from .staff import Staff
    from .user import User


class CashbackBalance(TimestampMixin, Base):
    __tablename__ = "cashback_balances"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))

    user: Mapped["User"] = relationship("User", back_populates="cashback_wallet")


class CashbackTransaction(Base):
    __tablename__ = "cashback_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[CashbackSource] = mapped_column(Enum(CashbackSource, name="cashback_source"))
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="cashback_transactions")
    staff: Mapped["Staff"] = relationship("Staff")
