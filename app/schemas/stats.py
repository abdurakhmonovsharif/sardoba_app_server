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


class WaiterLeaderboardRow(BaseModel):
    staff_id: int
    staff_name: str
    clients_count: int


class LeaderboardUser(BaseModel):
    id: int
    name: str | None
    phone: str
    waiter_id: int | None
    cashback_balance: Decimal | None = None


class TopUserLeaderboardRow(BaseModel):
    user: LeaderboardUser
    total_cashback: Decimal
    transactions: int
