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


class CashbackUseRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(..., gt=0)


class CashbackUseResponse(BaseModel):
    can_use_cashback: bool
    balance: Decimal
    message: dict[str, str]


class LoyaltySummary(BaseModel):
    cashback_balance: Decimal


class CashbackHistoryResponse(BaseModel):
    loyalty: LoyaltySummary
    transactions: list[CashbackRead]


class LoyaltyAnalytics(BaseModel):
    totalUsers: int
    totalCashbackBalance: float
    averageCashbackBalance: float
