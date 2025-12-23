from datetime import datetime
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field
from .common import Pagination


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


class NotificationTokenRegister(BaseModel):
    deviceToken: str | None = Field(default=None, alias="deviceToken")
    deviceType: Literal["ios", "android"] = Field(..., alias="deviceType")
    language: str = Field(default="ru", alias="language")

    class Config:
        allow_population_by_field_name = True
        min_anystr_length = 1


class UserNotificationRead(BaseModel):
    id: int
    title: str
    description: str
    type: str | None = None
    payload: dict[str, Any] | None = None
    language: str
    is_read: bool
    is_sent: bool
    sent_at: datetime | None
    created_at: datetime

    class Config:
        orm_mode = True


class AdminNotificationCreate(BaseModel):
    userIds: list[int] = Field(..., alias="userIds")
    title: str
    description: str
    notificationType: str | None = Field(default=None, alias="notificationType")
    payload: dict[str, Any] | None = Field(default=None, alias="payload")
    language: str = Field(default="ru", alias="language")

    class Config:
        allow_population_by_field_name = True


class NotificationListResponse(BaseModel):
    pagination: Pagination
    items: list[NotificationRead]


class UserNotificationListResponse(BaseModel):
    unread_count: int
    items: list[UserNotificationRead]
