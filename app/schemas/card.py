from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CardRead(BaseModel):
    id: int
    user_id: int
    card_number: str
    card_track: str
    iiko_card_id: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True
