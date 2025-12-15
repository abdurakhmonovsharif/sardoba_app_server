from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Card(TimestampMixin, Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    card_track: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    iiko_card_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="cards")
