from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, validator

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

    class Config:
        orm_mode = True

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
