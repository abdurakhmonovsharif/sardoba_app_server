import logging
from decimal import Decimal
from typing import Optional

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
from app.schemas.iiko import IikoTransactionType

from . import exceptions
from .push_notification_service import PushNotificationService


GIFT_REFILL_AMOUNT = Decimal("35000")


class CashbackService:
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
            transaction_type=IikoTransactionType.ACCRUAL,
        )

    def adjust_cashback_balance(
        self,
        *,
        user: User,
        amount: Optional[Decimal],
        branch_id: int | None,
        source: CashbackSource,
        staff_id: int | None,
        transaction_type: IikoTransactionType,
        balance_override: Decimal | None = None,
        earn_points: bool = True,
        event_id: str | None = None,
        uoc_id: str | None = None,
        push_only_notification: bool = False,
    ) -> Optional[CashbackTransaction]:
        """
        Safely adjusts cashback balance based on IIKO transaction type.
        NEVER raises on webhook events.
        """

        if transaction_type == IikoTransactionType.SIMPLE_PUSH:
            self._logger.info(
                "SimplePush received. No balance change. user_id=%s event_id=%s",
                user.id,
                event_id,
            )
            return None

        balance_required_types = {
            IikoTransactionType.ACCRUAL,
            IikoTransactionType.PAY_FROM_WALLET,
            IikoTransactionType.CORRECTION,
            IikoTransactionType.REFILL_WALLET,
            IikoTransactionType.REFILL_WALLET_FROM_ORDER,
            IikoTransactionType.WELCOMEBONUS,
        }

        if transaction_type in balance_required_types and amount is None:
            self._logger.warning(
                "Balance change skipped: amount is None | "
                "user_id=%s type=%s event_id=%s uoc_id=%s",
                user.id,
                transaction_type,
                event_id,
                uoc_id,
            )
            return None

        amount = amount or Decimal("0")

        try:
            balance = (
                self.db.query(CashbackBalance)
                .filter(CashbackBalance.user_id == user.id)
                .with_for_update()
                .first()
            )

            if not balance:
                balance = CashbackBalance(
                    user_id=user.id,
                    balance=Decimal("0.00"),
                    points=Decimal("0.00"),
                )
                self.db.add(balance)
                self.db.flush()

            zero = Decimal("0.00")
            current_balance = balance.balance or zero

            if balance_override is not None:
                new_balance = balance_override
            else:
                if transaction_type == IikoTransactionType.PAY_FROM_WALLET:
                    new_balance = current_balance - amount.copy_abs()
                else:
                    new_balance = current_balance + amount

            balance.balance = new_balance
            balance.points = balance.points or zero

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

            self.db.add(cashback)
            self.db.flush()

            if transaction_type == IikoTransactionType.WELCOMEBONUS and not user.giftget:
                user.giftget = True
                self.db.add(user)

            self.db.commit()
            self.db.refresh(cashback)

        except Exception:
            self.db.rollback()
            self._logger.exception(
                "Failed to adjust cashback balance | user_id=%s type=%s",
                user.id,
                transaction_type,
            )
            return None

        try:
            PushNotificationService(self.db).notify_cashback_change(
                user.id,
                amount,
                persist=not push_only_notification,
            )
        except Exception as exc:
            self._logger.warning(
                "Push notification failed | user_id=%s error=%s",
                user.id,
                exc,
            )

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
        return {
            "cashback_balance": user.cashback_balance,
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
                func.coalesce(func.sum(CashbackTransaction.amount), 0).label("total_cashback"),
                func.count(CashbackTransaction.id).label("transactions"),
            )
            .outerjoin(CashbackTransaction, CashbackTransaction.user_id == User.id)
            .filter(User.is_deleted == False)  # noqa: E712
            .group_by(User.id, User.name, User.phone, User.waiter_id)
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
                        "cashback_balance": None,
                    },
                    "total_cashback": data["total_cashback"],
                    "transactions": data["transactions"],
                }
            )
        return leaderboard

    def loyalty_analytics_summary(self, near_limit: int = 5) -> dict:
        total_users = (
            self.db.query(func.count(User.id))
            .filter(User.is_deleted == False)  # noqa: E712
            .scalar()
            or 0
        )
        total_balance = (
            self.db.query(func.coalesce(func.sum(CashbackBalance.balance), 0))
            .scalar()
            or Decimal("0")
        )
        users_with_balance = (
            self.db.query(func.count(CashbackBalance.user_id))
            .scalar()
            or 0
        )
        avg_balance = (
            total_balance / users_with_balance if users_with_balance else Decimal("0")
        )

        return {
            "totalUsers": int(total_users),
            "totalCashbackBalance": float(total_balance),
            "averageCashbackBalance": float(avg_balance),
        }
