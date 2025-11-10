from decimal import Decimal

from pydantic import BaseModel


class WaiterStats(BaseModel):
    waiter_id: int
    waiter_name: str
    total_cashback: Decimal


class TopUserStats(BaseModel):
    user_id: int
    user_name: str | None
    phone: str
    total_cashback: Decimal
