from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: str


class NotificationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None

    def dict(self, *args, **kwargs):  # ensure Pydantic v1 to include exclude_unset use
        return super().dict(*args, **kwargs)


class NotificationRead(BaseModel):
    id: int
    title: str
    description: str
    created_at: datetime

    class Config:
        orm_mode = True
