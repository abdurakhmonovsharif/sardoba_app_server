from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, root_validator, validator

from app.models.enums import SardobaBranch, StaffRole
from .common import Pagination


class ClientOTPRequest(BaseModel):
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    purpose: str = Field(default="login")


class ClientOTPVerify(BaseModel):
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    code: str = Field(..., min_length=4, max_length=8)
    name: Optional[str] = Field(default=None, max_length=150)
    waiter_referral_code: Optional[str] = Field(default=None, max_length=12)
    purpose: str = Field(default="login")
    date_of_birth: Optional[date] = None

    @validator("date_of_birth", pre=True)
    def validate_date_of_birth(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError as exc:
            raise ValueError("date_of_birth must be in format dd.mm.yyyy") from exc


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
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class WaiterCreateRequest(BaseModel):
    name: str = Field(..., max_length=150)
    phone: str = Field(..., regex=r"^\+?\d{7,15}$")
    password: str = Field(..., min_length=6)
    branch_id: Optional[SardobaBranch] = None


class WaiterUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    phone: Optional[str] = Field(default=None, regex=r"^\+?\d{7,15}$")
    password: Optional[str] = Field(default=None, min_length=6)
    branch_id: Optional[SardobaBranch] = None

    @root_validator(pre=True)
    def check_at_least_one(cls, values):
        data = values or {}
        if not any(field in data for field in ("name", "phone", "password", "branch_id")):
            raise ValueError("At least one field must be provided for update")
        return values


class StaffListResponse(BaseModel):
    pagination: Pagination
    items: list[StaffRead]


class RefreshRequest(BaseModel):
    refresh_token: str
