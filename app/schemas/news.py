from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NewsBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: str
    image_url: Optional[str] = Field(default=None, max_length=500)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    priority: int = 0


class NewsCreate(NewsBase):
    pass


class NewsUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    priority: Optional[int] = None


class NewsRead(NewsBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
