from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

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


class CashbackUseRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(..., gt=0)


class CashbackUseResponse(BaseModel):
    can_use_cashback: bool
    balance: Decimal
    message: dict[str, str]


class LoyaltySummary(BaseModel):
    level: Optional[str]
    cashback_balance: Decimal

    points_total: Decimal
    current_level_points: Decimal
    current_level_min_points: Decimal
    current_level_max_points: Optional[Decimal]

    next_level: Optional[str]
    next_level_required_points: Optional[Decimal]
    points_to_next_level: Decimal

    is_max_level: bool

    cashback_percent: Decimal
    next_level_cashback_percent: Optional[Decimal]


class CashbackHistoryResponse(BaseModel):
    loyalty: LoyaltySummary
    transactions: list[CashbackRead]


class TierCount(BaseModel):
    tier: str
    users: int


class NearNextTier(BaseModel):
    user: dict[str, Any]
    missingPoints: float


class LoyaltyAnalytics(BaseModel):
    tierCounts: list[TierCount]
    nearNextTier: list[NearNextTier]
    averagePoints: float
