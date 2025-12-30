from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel
from pydantic import Field


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Pagination(BaseModel):
    page: int
    size: int
    total: int


class AuthLogMeta(BaseModel):
    data: Optional[dict[str, Any]] = None


class AuthLogActor(BaseModel):
    id: Optional[int]
    type: str
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None


class AuthLogRead(BaseModel):
    id: int
    actor_type: str
    actor_id: Optional[int]
    event: str
    status: Optional[str] = None
    phone: Optional[str]
    action: str
    ip: Optional[str]
    user_agent: Optional[str]
    metadata: Optional[dict[str, Any]] = Field(default=None, alias="meta")
    user: Optional[AuthLogActor] = None
    created_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class AuthLogListResponse(BaseModel):
    pagination: Pagination
    items: list[AuthLogRead]
