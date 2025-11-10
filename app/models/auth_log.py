from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .enums import AuthActorType, AuthAction


class AuthLog(Base):
    __tablename__ = "auth_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_type: Mapped[AuthActorType] = mapped_column(
        Enum(AuthActorType, name="auth_actor_type"), default=AuthActorType.CLIENT
    )
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[AuthAction] = mapped_column(
        Enum(AuthAction, name="auth_action"), default=AuthAction.LOGIN
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
