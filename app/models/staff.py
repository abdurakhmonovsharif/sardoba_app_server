from __future__ import annotations

from typing import Optional

from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import StaffRole


class Staff(TimestampMixin, Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[StaffRole] = mapped_column(Enum(StaffRole, name="staff_role"), default=StaffRole.WAITER)
    branch_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    referral_code: Mapped[Optional[str]] = mapped_column(String(12), unique=True, nullable=True, index=True)

    clients: Mapped[list["User"]] = relationship("User", back_populates="waiter")
