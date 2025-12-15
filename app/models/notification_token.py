from typing import Literal

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class NotificationDeviceToken(TimestampMixin, Base):
    __tablename__ = "notification_device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_token: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    device_type: Mapped[Literal["ios", "android"]] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru", server_default="'ru'")

    user = relationship("User", back_populates="notification_tokens")
