from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, root_validator, validator

from app.core.phone import normalize_uzbek_phone
from app.models.enums import SardobaBranch, StaffRole
from .common import Pagination


class ClientOTPRequest(BaseModel):
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    purpose: str = Field(default="login")

    @validator("phone", pre=True)
    def normalize_phone(cls, value: str) -> str:
        try:
            return normalize_uzbek_phone(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ClientOTPVerify(BaseModel):
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    code: str = Field(..., min_length=4, max_length=8)
    name: Optional[str] = Field(default=None, max_length=150)
    waiter_referral_code: Optional[str] = Field(default=None, max_length=12, alias="referral_code")
    purpose: str = Field(default="login")
    date_of_birth: Optional[date] = None

    @validator("phone", pre=True)
    def normalize_phone(cls, value: str) -> str:
        try:
            return normalize_uzbek_phone(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @validator("date_of_birth", pre=True)
    def validate_date_of_birth(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        str_value = str(value).strip()
        # Accept both dd.mm.yyyy and yyyy-mm-dd (ISO) formats
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str_value, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(str_value).date()
        except ValueError as exc:
            raise ValueError("date_of_birth must be in format dd.mm.yyyy or yyyy-mm-dd") from exc

    class Config:
        allow_population_by_field_name = True


class StaffLoginRequest(BaseModel):
    phone: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)

    @validator("phone")
    def normalize_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("phone cannot be blank")
        return normalized


class StaffChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


class StaffCreateRequest(BaseModel):
    name: str = Field(..., max_length=150)
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    password: str = Field(..., min_length=6)
    role: StaffRole
    branch_id: Optional[SardobaBranch] = None


class StaffRead(BaseModel):
    id: int
    name: str
    phone: str
    role: StaffRole
    branch_id: Optional[SardobaBranch]
    referral_code: Optional[str]
    clients_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class WaiterCreateRequest(BaseModel):
    name: str = Field(..., max_length=150)
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    password: str = Field(..., min_length=6)
    branch_id: Optional[SardobaBranch] = None
    referral_code: Optional[str] = Field(default=None, max_length=12)

    @validator("phone", pre=True)
    def normalize_phone(cls, value: str) -> str:
        if value is None:
            raise ValueError("phone cannot be empty")
        text = str(value).strip()
        if not text:
            raise ValueError("phone cannot be empty")
        has_plus = text.startswith("+")
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            raise ValueError("phone must contain digits")
        return f"+{digits}" if has_plus else digits


class WaiterUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    phone: Optional[str] = Field(default=None, regex=r"^\+?\d{7,15}$")
    password: Optional[str] = Field(default=None, min_length=6)
    branch_id: Optional[SardobaBranch] = None
    referral_code: Optional[str] = Field(default=None, max_length=12)

    @root_validator(pre=True)
    def check_at_least_one(cls, values):
        data = values or {}
        if not any(field in data for field in ("name", "phone", "password", "branch_id", "referral_code")):
            raise ValueError("At least one field must be provided for update")
        return values


class StaffListResponse(BaseModel):
    pagination: Pagination
    items: list[StaffRead]


class RefreshRequest(BaseModel):
    refresh_token: str
