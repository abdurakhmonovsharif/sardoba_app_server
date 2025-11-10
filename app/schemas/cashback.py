from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import CashbackSource, SardobaBranch


class CashbackCreate(BaseModel):
    user_id: int
    amount: Decimal = Field(..., gt=0)
    branch_id: Optional[SardobaBranch] = None
    source: CashbackSource


class CashbackRead(BaseModel):
    id: int
    user_id: int
    amount: Decimal
    branch_id: Optional[SardobaBranch]
    source: CashbackSource
    staff_id: Optional[int]
    balance_after: Decimal
    created_at: datetime

    class Config:
        orm_mode = True


class LoyaltySummary(BaseModel):
    level: str
    current_points: str
    current_level_min: str
    current_level_max: str
    current_level_points: str
    next_level: Optional[str]
    next_level_points: Optional[str]
    points_to_next: Optional[str]
    is_max_level: bool


class CashbackHistoryResponse(BaseModel):
    loyalty: LoyaltySummary
    transactions: list[CashbackRead]
