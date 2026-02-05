from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class IikoSyncJob(TimestampMixin, Base):
    __tablename__ = "iiko_sync_jobs"
    __table_args__ = (
        Index("ix_iiko_sync_jobs_status_next_retry_at", "status", "next_retry_at"),
        Index("ix_iiko_sync_jobs_user_operation", "user_id", "operation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default="8")
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
