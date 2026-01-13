from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional
from urllib.parse import urljoin

from pydantic import BaseModel, Field, root_validator, validator

from app.core.config import get_settings


PRIORITY_MAP = {
    "low": 0,
    "normal": 1,
    "medium": 1,
    "high": 2,
    "urgent": 3,
}


def _parse_date_str(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _parse_datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return _parse_date_str(text)
    return datetime.fromisoformat(text)


def _parse_priority_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("priority must not be blank")
    lowered = text.lower()
    if lowered in PRIORITY_MAP:
        return PRIORITY_MAP[lowered]
    if lowered.lstrip("-").isdigit():
        return int(lowered)
    raise ValueError("priority must be a number or one of low/medium/high")


def _absolute_public_url(base_url: str | None, path: str | None) -> str | None:
    if not path:
        return None
    stripped = path.strip()
    if not stripped:
        return None
    if stripped.startswith(("http://", "https://")):
        return stripped
    if not base_url:
        return stripped
    normalized_base = base_url.rstrip("/")
    return urljoin(normalized_base + "/", stripped.lstrip("/"))


class NewsBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: str
    image_url: Optional[str] = Field(default=None, max_length=500)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    priority: int = 0

    @validator("starts_at", "ends_at", pre=True)
    def _parse_dates(cls, value: Any) -> datetime | None:
        if value in (None, "", []):
            return None
        try:
            return _parse_datetime_value(value)
        except ValueError:
            raise ValueError("invalid datetime format")

    @validator("priority", pre=True, always=True)
    def _normalize_priority(cls, value: Any) -> int:
        if value in (None, "", []):
            return 0
        try:
            return _parse_priority_value(value)
        except ValueError:
            raise ValueError("priority must be a number or one of low/medium/high")


class NewsCreate(NewsBase):
    pass


class NewsUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    priority: Optional[int] = None

    @validator("starts_at", "ends_at", pre=True)
    def _parse_dates(cls, value: Any) -> datetime | None:
        if value in (None, "", []):
            return None
        try:
            return _parse_datetime_value(value)
        except ValueError:
            raise ValueError("invalid datetime format")

    @validator("priority", pre=True)
    def _normalize_priority(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return _parse_priority_value(value)
        except ValueError:
            raise ValueError("priority must be a number or one of low/medium/high")


class NewsRead(NewsBase):
    id: int
    created_at: datetime
    link: str

    @root_validator(pre=True)
    def _populate_public_links(cls, values: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        base_url = settings.PUBLIC_API_URL
        values["image_url"] = _absolute_public_url(base_url, values.get("image_url"))

        prefix = settings.API_V1_PREFIX.strip("/")
        prefix_path = f"/{prefix}" if prefix else ""
        news_id = values.get("id")
        if news_id is not None:
            news_path = f"{prefix_path}/news/{news_id}"
            values["link"] = _absolute_public_url(base_url, news_path)
        else:
            values["link"] = _absolute_public_url(base_url, prefix_path or "/news")
        return values

    class Config:
        orm_mode = True
