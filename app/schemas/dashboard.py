from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    totalClients: int
    activeWaiters: int
    cashbackIssued: float
    avgCashbackPerUser: float
    newsCount: int
    redisHealthy: bool
    postgresHealthy: bool
    queueHealthy: bool


class ActivityItem(BaseModel):
    id: str
    type: Literal["auth", "otp", "cashback", "news"]
    description: str
    created_at: datetime
    status: Literal["success", "warning", "error"]


class SystemHealth(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "down"]
    message: str
