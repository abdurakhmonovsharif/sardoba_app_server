from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DeletedPhone(Base):
    __tablename__ = "deleted_phones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    real_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    user = relationship("User")
