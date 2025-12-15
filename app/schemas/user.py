from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, validator

from .auth import StaffRead
from .cashback import CashbackRead, LoyaltySummary
from .common import Pagination


class UserRead(BaseModel):
    id: int
    name: Optional[str]
    phone: str
    waiter_id: Optional[int]
    date_of_birth: Optional[str]
    profile_photo_url: Optional[str]
    cashback_balance: Decimal
    level: str
    email: Optional[str]
    gender: Optional[str]
    surname: Optional[str]
    middle_name: Optional[str] = Field(default=None, alias="middleName")
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

    @validator("date_of_birth", pre=True)
    def format_date_of_birth(cls, value: Optional[date]):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.strftime("%d.%m.%Y")

    @validator("level", pre=True)
    def format_level(cls, value: Optional[str]):
        if value is None:
            return "Silver"
        raw = value.value if hasattr(value, "value") else value
        if isinstance(raw, str):
            return raw.capitalize()
        return str(raw)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    date_of_birth: Optional[date] = None
    profile_photo_url: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    surname: Optional[str] = None
    middle_name: Optional[str] = Field(default=None, alias="middleName")

    @validator("date_of_birth", pre=True)
    def parse_date_of_birth(cls, value: Optional[str]):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        str_value = str(value).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str_value, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(str_value).date()
        except ValueError as exc:
            raise ValueError("date_of_birth must be in format dd.mm.yyyy or yyyy-mm-dd") from exc


class UserListResponse(BaseModel):
    pagination: Pagination
    items: list[UserRead]


class UserDetail(UserRead):
    loyalty: Optional["LoyaltySummary"] = None
    transactions: list["CashbackRead"] = Field(default_factory=list)
    waiter: Optional[StaffRead] = None


class AdminUserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middleName: Optional[str] = Field(default=None, alias="middle_name")
    dob: Optional[date] = None
    waiter_id: Optional[int] = None
    profile_photo_url: Optional[str] = None

    @validator("dob", pre=True)
    def parse_dob(cls, value: Optional[str]):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        str_value = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(str_value, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(str_value).date()
        except ValueError as exc:
            raise ValueError("dob must be in format yyyy-mm-dd or dd.mm.yyyy") from exc
