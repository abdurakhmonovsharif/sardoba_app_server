from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    CashbackBalance,
    CashbackSource,
    CashbackTransaction,
    Staff,
    StaffRole,
    User,
)

from . import exceptions

TWOPLACES = Decimal("0.01")


class CashbackService:
    def __init__(self, db: Session):
        self.db = db

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

        balance = (
            self.db.query(CashbackBalance)
            .filter(CashbackBalance.user_id == user.id)
            .with_for_update()
            .first()
        )
        if not balance:
            balance = CashbackBalance(user_id=user.id, balance=Decimal("0.00"))
            self.db.add(balance)
            self.db.flush()

        current_balance = balance.balance or Decimal("0.00")
        new_balance = current_balance + amount
        balance.balance = new_balance

        level_changed = user.apply_level_from_balance(new_balance)

        cashback = CashbackTransaction(
            user_id=user.id,
            staff_id=actor.id,
            amount=amount,
            branch_id=branch_id,
            source=source,
            balance_after=new_balance,
        )

        self.db.add(cashback)
        if level_changed:
            self.db.add(user)
        self.db.flush()
        self.db.commit()
        self.db.refresh(cashback)
        return cashback

    def get_user_cashbacks(self, *, user_id: int, limit: int | None = None) -> list[CashbackTransaction]:
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
        return {
            "level": metrics["level"].value if metrics["level"] else None,
            "current_points": self._decimal_to_str(metrics["balance"]),
            "current_level_min": self._decimal_to_str(metrics["current_level_floor"]),
            "current_level_max": self._decimal_to_str(metrics["current_level_cap"]),
            "current_level_points": self._decimal_to_str(metrics["progress_in_level"]),
            "next_level": metrics["next_level"].value if metrics["next_level"] else None,
            "next_level_points": self._decimal_to_str(metrics["next_level_threshold"]),
            "points_to_next": self._decimal_to_str(metrics["points_to_next"]),
            "is_max_level": metrics["next_level"] is None,
        }

    def waiter_stats(self) -> list[dict]:
        rows = (
            self.db.query(
                Staff.id.label("waiter_id"),
                Staff.name.label("waiter_name"),
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label("total_cashback"),
            )
            .join(User, User.waiter_id == Staff.id)
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .filter(Staff.role == StaffRole.WAITER)
            .group_by(Staff.id, Staff.name)
            .all()
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    def _decimal_to_str(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value.quantize(TWOPLACES), "f")

    def top_users(self, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.name.label("user_name"),
                User.phone,
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label("total_cashback"),
            )
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .group_by(User.id, User.name, User.phone)
            .order_by(func.coalesce(func.sum(CashbackTransaction.amount), 0).desc())
            .limit(limit)
            .all()
        )
        return [dict(row._mapping) for row in rows]
