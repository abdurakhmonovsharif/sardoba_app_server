import logging
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CashbackBalance,
    CashbackSource,
    CashbackTransaction,
    Staff,
    StaffRole,
    User,
    UserLevel,
)

from . import exceptions
from .push_notification_service import PushNotificationService

TWOPLACES = Decimal("0.01")


class CashbackService:
    LEVEL_REWARD_SETTINGS = {
        UserLevel.SILVER: {
            "cashback_percent": Decimal("0.02"),
            "points_divisor": Decimal("2"),
        },
        UserLevel.GOLD: {
            "cashback_percent": Decimal("0.025"),
            "points_divisor": Decimal("3"),
        },
        UserLevel.PREMIUM: {
            "cashback_percent": Decimal("0.03"),
            "points_divisor": Decimal("5"),
        },
        UserLevel.VIP: {
            "cashback_percent": Decimal("0.035"),
            "points_divisor": Decimal("8"),
        },
    }

    def __init__(self, db: Session):
        self.db = db
        self._min_cashback_use = Decimal("50000")
        self._logger = logging.getLogger(__name__)

    def add_cashback(
        self,
        *,
        actor: Staff,
        user_id: int,
        amount: Decimal,
        branch_id: int | None,
        source: CashbackSource,
    ) -> CashbackTransaction:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can add cashback")

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise exceptions.NotFoundError("User not found")

        return self.adjust_cashback_balance(
            user=user,
            amount=amount,
            branch_id=branch_id,
            source=source,
            staff_id=actor.id,
        )

    def adjust_cashback_balance(
        self,
        *,
        user: User,
        amount: Decimal,
        branch_id: int | None,
        source: CashbackSource,
        staff_id: int | None,
        balance_override: Decimal | None = None,
        earn_points: bool = True,
        event_id: str | None = None,
        uoc_id: str | None = None,
    ) -> CashbackTransaction:

        balance = (
            self.db.query(CashbackBalance)
            .filter(CashbackBalance.user_id == user.id)
            .with_for_update()
            .first()
        )
        if not balance:
            balance = CashbackBalance(
                user_id=user.id, balance=Decimal("0.00"), points=Decimal("0.00")
            )
            self.db.add(balance)
            self.db.flush()

        zero = Decimal("0")
        current_balance = balance.balance or zero
        if balance_override is not None:
            new_balance = balance_override
        else:
            new_balance = current_balance + amount
        balance.balance = new_balance

        points_before = balance.points or zero
        earned_points = zero
        if earn_points and amount > zero:
            divisor = self._settings_for_level(user.level)["points_divisor"]
            if divisor > zero:
                earned_points = (amount / divisor).to_integral_value(
                    rounding=ROUND_DOWN
                )
        balance.points = points_before + earned_points
        level_changed = user.apply_level_from_points(balance.points)
        cashback = CashbackTransaction(
            user_id=user.id,
            staff_id=staff_id,
            amount=amount,
            branch_id=branch_id,
            source=source,
            balance_after=new_balance,
            iiko_event_id=event_id,
            iiko_uoc_id=uoc_id,
        )
        print("cashback = ", cashback.__dict__)
        self.db.add(cashback)
        if level_changed:
            self.db.add(user)
        self.db.flush()
        self.db.commit()
        self.db.refresh(cashback)
        try:
            PushNotificationService(self.db).notify_cashback_change(user.id, amount)
        except Exception as exc:
            self._logger.warning("Failed to send push for cashback change: %s", exc)
        return cashback

    def get_user_cashbacks(
        self, *, user_id: int, limit: int | None = None
    ) -> list[CashbackTransaction]:
        query = (
            self.db.query(CashbackTransaction)
            .filter(CashbackTransaction.user_id == user_id)
            .order_by(CashbackTransaction.created_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def loyalty_summary(self, *, user: User) -> dict:
        metrics = user.loyalty_metrics()
        level = metrics["level"]
        next_level = metrics["next_level"]
        points_total = metrics["points"]
        current_floor = metrics["current_level_floor"]
        current_progress = metrics["progress_in_level"]
        next_level_threshold = metrics["next_level_threshold"]
        points_to_next = Decimal("0")
        if next_level_threshold is not None:
            delta = next_level_threshold - points_total
            points_to_next = delta if delta >= Decimal("0") else Decimal("0")
        current_percent = self._settings_for_level(level)["cashback_percent"]
        next_level_percent = (
            self._settings_for_level(next_level)["cashback_percent"]
            if next_level
            else None
        )
        return {
            "level": level.value if level else None,
            "cashback_balance": metrics["balance"],
            "points_total": points_total,
            "current_level_points": current_progress,
            "current_level_min_points": current_floor,
            "current_level_max_points": next_level_threshold,
            "next_level": next_level.value if next_level else None,
            "next_level_required_points": next_level_threshold,
            "points_to_next_level": (
                Decimal("0") if next_level is None else points_to_next
            ),
            "is_max_level": next_level is None,
            "cashback_percent": self._percent_value(current_percent),
            "next_level_cashback_percent": self._percent_value(next_level_percent),
        }

    def check_cashback_payment(self, *, user_id: int, amount: Decimal) -> Decimal:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise exceptions.NotFoundError("User not found")
        if amount < self._min_cashback_use:
            raise exceptions.ServiceError(
                "Cashback payment amount must be at least 50,000 UZS."
            )
        if user.cashback_balance < self._min_cashback_use:
            raise exceptions.ServiceError(
                "Cashback balance must be at least 50,000 UZS to pay with cashback."
            )
        if user.cashback_balance < amount:
            raise exceptions.ServiceError("Insufficient cashback balance.")
        return user.cashback_balance

    def waiter_stats(self) -> list[dict]:
        rows = (
            self.db.query(
                Staff.id.label("waiter_id"),
                Staff.name.label("waiter_name"),
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label(
                    "total_cashback"
                ),
            )
            .join(User, User.waiter_id == Staff.id)
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .filter(Staff.role == StaffRole.WAITER)
            .group_by(Staff.id, Staff.name)
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def waiter_leaderboard(self) -> list[dict]:
        rows = (
            self.db.query(
                Staff.id.label("staff_id"),
                Staff.name.label("staff_name"),
                func.count(User.id).label("clients_count"),
            )
            .join(User, User.waiter_id == Staff.id)
            .filter(Staff.role == StaffRole.WAITER, User.is_deleted == False)  # noqa: E712
            .group_by(Staff.id, Staff.name)
            .order_by(func.count(User.id).desc())
            .all()
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    def _decimal_to_str(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value.quantize(TWOPLACES), "f")

    def _percent_to_str(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return self._decimal_to_str(value * Decimal("100"))

    def _settings_for_level(self, level: UserLevel | None) -> dict[str, Decimal]:
        if level is None:
            return {"points_divisor": Decimal("2")}
        return self.LEVEL_REWARD_SETTINGS.get(
            level, self.LEVEL_REWARD_SETTINGS[UserLevel.SILVER]
        )

    def _percent_value(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return (value * Decimal("100")).quantize(TWOPLACES)

    def top_users(self, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.name.label("user_name"),
                User.phone,
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label(
                    "total_cashback"
                ),
            )
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .group_by(User.id, User.name, User.phone)
            .order_by(func.coalesce(func.sum(CashbackTransaction.amount), 0).desc())
            .limit(limit)
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def top_users_leaderboard(self, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.name.label("user_name"),
                User.phone,
                User.waiter_id,
                User.level,
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label("total_cashback"),
                func.count(CashbackTransaction.id).label("transactions"),
            )
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .filter(User.is_deleted == False)  # noqa: E712
            .group_by(User.id, User.name, User.phone, User.waiter_id, User.level)
            .order_by(func.coalesce(func.sum(CashbackTransaction.amount), 0).desc())
            .limit(limit)
            .all()
        )
        leaderboard: list[dict] = []
        for row in rows:
            data = row._mapping
            leaderboard.append(
                {
                    "user": {
                        "id": data["user_id"],
                        "name": data["user_name"],
                        "phone": data["phone"],
                        "waiter_id": data["waiter_id"],
                        "level": data["level"].value if data["level"] else None,
                        "cashback_balance": None,
                    },
                    "total_cashback": data["total_cashback"],
                    "transactions": data["transactions"],
                }
            )
        return leaderboard

    def loyalty_analytics_summary(self, near_limit: int = 5) -> dict:
        tier_counts = {level: 0 for level in UserLevel}
        rows = (
            self.db.query(User.level, func.count(User.id))
            .filter(User.is_deleted == False)  # noqa: E712
            .group_by(User.level)
            .all()
        )
        for level, count in rows:
            tier_counts[level] = count

        average_points = (
            self.db.query(func.coalesce(func.avg(CashbackBalance.points), 0))
            .scalar()
            or Decimal("0")
        )

        users = (
            self.db.query(User)
            .options(selectinload(User.cashback_wallet))
            .filter(User.is_deleted == False)  # noqa: E712
            .all()
        )

        near_next: list[dict] = []
        for user in users:
            metrics = user.loyalty_metrics()
            next_level = metrics.get("next_level")
            missing = metrics.get("points_to_next")
            if next_level is None or missing is None:
                continue
            missing_normalized = self._normalize_points(missing)
            if missing_normalized <= Decimal("0"):
                continue
            near_next.append(
                {
                    "user": self._serialize_loyalty_user(user, metrics),
                    "missingPoints": float(missing_normalized),
                }
            )

        near_next.sort(key=lambda item: item["missingPoints"])
        near_next = near_next[:near_limit]

        tier_counts_payload = [
            {
                "tier": level.value.title(),
                "users": int(tier_counts.get(level, 0)),
            }
            for level in UserLevel
        ]

        return {
            "tierCounts": tier_counts_payload,
            "nearNextTier": near_next,
            "averagePoints": float(average_points),
        }

    @staticmethod
    def _normalize_points(value: Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _serialize_loyalty_user(self, user: User, metrics: dict) -> dict:
        name = user.name or ""
        first_name = name.split(" ", 1)[0] if name else ""
        last_name = name.split(" ", 1)[1] if name and " " in name else ""
        next_level = metrics.get("next_level")
        next_level_threshold = metrics.get("next_level_threshold")
        return {
            "id": user.id,
            "name": name or None,
            "first_name": first_name or None,
            "last_name": last_name or None,
            "phone": user.phone,
            "cashback_balance": float(metrics.get("balance") or 0),
            "level": metrics.get("level").value if metrics.get("level") else None,
            "loyalty": {
                "current_points": float(metrics.get("points") or 0),
                "current_level": metrics.get("level").value if metrics.get("level") else None,
                "next_level": next_level.value if next_level else None,
                "next_level_threshold": float(next_level_threshold)
                if next_level_threshold is not None
                else None,
                "progress_percent": None,
            },
            "is_active": not bool(getattr(user, "is_deleted", False)),
            "created_at": getattr(user, "created_at", None),
        }
