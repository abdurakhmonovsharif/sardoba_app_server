from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from .common import Pagination


class FileRead(BaseModel):
    name: str
    url: str
    size: int
    created_at: datetime
    type: str  # 'profile_photo' or 'news_image'


class FileListResponse(BaseModel):
    pagination: Pagination
    items: list[FileRead]
