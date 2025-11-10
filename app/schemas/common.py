from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


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


class AuthLogRead(BaseModel):
    id: int
    actor_type: str
    actor_id: Optional[int]
    phone: Optional[str]
    action: str
    ip: Optional[str]
    user_agent: Optional[str]
    meta: Optional[dict[str, Any]]
    created_at: datetime

    class Config:
        orm_mode = True
