import logging
from datetime import datetime, timezone
from decimal import Decimal

from redis.exceptions import RedisError
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.cache import RedisCacheBackend, cache_manager
from app.models import (
    AuthAction,
    AuthLog,
    CashbackBalance,
    CashbackTransaction,
    News,
    Staff,
    StaffRole,
    User,
)


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self._logger = logging.getLogger(__name__)

    def get_metrics(self) -> dict:
        total_clients = (
            self.db.query(func.count(User.id))
            .filter(User.is_deleted == False)  # noqa: E712
            .scalar()
            or 0
        )
        active_waiters = (
            self.db.query(func.count(Staff.id))
            .filter(Staff.role == StaffRole.WAITER)
            .scalar()
            or 0
        )
        cashback_outstanding = (
            self.db.query(func.coalesce(func.sum(CashbackBalance.balance), 0))
            .scalar()
            or Decimal("0")
        )
        cashback_total = float(cashback_outstanding)
        avg_cashback = cashback_total / total_clients if total_clients else 0.0

        redis_ok = self._check_redis()
        postgres_ok = self._check_postgres()
        queue_ok = redis_ok  # current queues piggyback on redis availability

        return {
            "totalClients": int(total_clients),
            "activeWaiters": int(active_waiters),
            "cashbackIssued": cashback_total,
            "avgCashbackPerUser": float(avg_cashback),
            "newsCount": self._active_news_count(),
            "redisHealthy": redis_ok,
            "postgresHealthy": postgres_ok,
            "queueHealthy": queue_ok,
        }

    def recent_activity(self, limit: int = 10) -> list[dict]:
        events: list[dict] = []

        auth_logs = (
            self.db.query(AuthLog)
            .order_by(AuthLog.created_at.desc())
            .limit(limit)
            .all()
        )
        for log in auth_logs:
            events.append(self._map_auth_log(log))

        cashback_events = (
            self.db.query(CashbackTransaction)
            .order_by(CashbackTransaction.created_at.desc())
            .limit(limit)
            .all()
        )
        for txn in cashback_events:
            events.append(self._map_cashback(txn))

        news_events = (
            self.db.query(News)
            .order_by(News.created_at.desc())
            .limit(limit)
            .all()
        )
        for item in news_events:
            events.append(
                {
                    "id": f"news-{item.id}",
                    "type": "news",
                    "description": f"News published: {item.title}",
                    "created_at": item.created_at,
                    "status": "success",
                }
            )

        events.sort(key=lambda e: e["created_at"], reverse=True)
        return events[:limit]

    def system_health(self) -> list[dict]:
        redis_ok = self._check_redis()
        postgres_ok = self._check_postgres()
        queue_ok = redis_ok
        return [
            {
                "name": "PostgreSQL",
                "status": "healthy" if postgres_ok else "down",
                "message": "DB reachable" if postgres_ok else "Connection failed",
            },
            {
                "name": "Redis cache",
                "status": "healthy" if redis_ok else "degraded",
                "message": "Cache backend responding" if redis_ok else "Fallback cache active",
            },
            {
                "name": "Background queue",
                "status": "healthy" if queue_ok else "degraded",
                "message": "Uses Redis-backed queues" if queue_ok else "Queue unavailable",
            },
        ]

    def _active_news_count(self) -> int:
        now = datetime.now(tz=timezone.utc)
        return (
            self.db.query(func.count(News.id))
            .filter(
                (News.starts_at.is_(None) | (News.starts_at <= now)),
                (News.ends_at.is_(None) | (News.ends_at >= now)),
            )
            .scalar()
            or 0
        )

    def _check_redis(self) -> bool:
        try:
            backend = cache_manager.get_backend()
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.warning("Cache backend unavailable: %s", exc)
            return False
        if isinstance(backend, RedisCacheBackend):
            try:
                backend.client.ping()
                return True
            except RedisError as exc:
                self._logger.warning("Redis health check failed: %s", exc)
                return False
        # In-memory cache is considered degraded but available.
        return True

    def _check_postgres(self) -> bool:
        try:
            self.db.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover - best effort
            self._logger.warning("Postgres health check failed: %s", exc)
            return False

    def _map_auth_log(self, log: AuthLog) -> dict:
        action = log.action
        actor = log.actor_type.value if hasattr(log.actor_type, "value") else str(log.actor_type)
        status = "error" if action == AuthAction.FAILED_LOGIN else "success"
        event_type = (
            "otp" if action in {AuthAction.OTP_REQUEST, AuthAction.OTP_VERIFICATION} else "auth"
        )
        phone = log.phone or "unknown"
        if action == AuthAction.LOGIN:
            description = f"{actor.title()} login for {phone}"
        elif action == AuthAction.LOGOUT:
            description = f"{actor.title()} logout for {phone}"
        elif action == AuthAction.OTP_REQUEST:
            description = f"OTP requested for {phone}"
        elif action == AuthAction.OTP_VERIFICATION:
            description = f"OTP verified for {phone}"
        elif action == AuthAction.FAILED_LOGIN:
            description = f"Failed login attempt for {phone}"
        else:
            description = f"Auth event ({action.value}) for {phone}"
        return {
            "id": f"auth-{log.id}",
            "type": event_type,
            "description": description,
            "created_at": log.created_at,
            "status": status,
        }

    def _map_cashback(self, txn: CashbackTransaction) -> dict:
        amount = Decimal(txn.amount)
        direction = "granted" if amount >= 0 else "deducted"
        status = "success" if amount >= 0 else "warning"
        staff_part = f" by staff #{txn.staff_id}" if txn.staff_id else ""
        description = (
            f"Cashback {direction}: {abs(amount)} UZS for user #{txn.user_id}{staff_part}"
        )
        return {
            "id": f"cashback-{txn.id}",
            "type": "cashback",
            "description": description,
            "created_at": txn.created_at,
            "status": status,
        }
