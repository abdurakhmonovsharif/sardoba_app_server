import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models import CashbackSource, User
from app.schemas import IikoTransactionType, IikoWebhookPayload
from app.services import CashbackService

router = APIRouter(prefix="/iiko", tags=["iiko"])
logger = logging.getLogger("iiko.webhook")


def _determine_amount(payload: IikoWebhookPayload) -> Decimal:
    raw = payload.sum
    if payload.transactionType == IikoTransactionType.ACCRUAL:
        return abs(raw)
    if payload.transactionType == IikoTransactionType.PAY_FROM_WALLET:
        return -abs(raw)
    return raw


def _find_user_for_identifiers(
    db: Session, *, wallet_id: str | None, customer_id: str | None, phone: str | None
) -> User | None:
    conditions = []
    if wallet_id:
        conditions.append(User.iiko_wallet_id == wallet_id)
    if customer_id:
        conditions.append(User.iiko_customer_id == customer_id)
    if not conditions and phone:
        return (
            db.query(User)
            .filter(User.phone == phone, User.is_deleted == False)
            .first()
        )
    if not conditions:
        return None
    query = db.query(User)
    if len(conditions) == 1:
        return query.filter(conditions[0], User.is_deleted == False).first()
    return query.filter(or_(*conditions), User.is_deleted == False).first()


@router.post("/webhook")
async def iiko_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str | int]:
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
    logger.info("Incoming iiko webhook body: %s", body_text)

    if not body_text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Request body is empty")

    try:
        payload = IikoWebhookPayload.parse_raw(body_text)
    except ValidationError as exc:
        logger.warning("Invalid iiko webhook payload: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc

    if not payload.walletId and not payload.customerId:
        logger.warning(
            "Webhook missing identifiers; body=%s",
            body_text,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="walletId or customerId is required to locate the user",
        )
    user = _find_user_for_identifiers(
        db, wallet_id=payload.walletId, customer_id=payload.customerId, phone=payload.phone
    )
    if not user:
        logger.warning(
            "User not found for webhook; walletId=%s customerId=%s body=%s",
            payload.walletId,
            payload.customerId,
            body_text,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    amount = _determine_amount(payload)
    balance_override = None
    if payload.balance is not None:
        balance_override = Decimal(str(payload.balance))
    if amount == Decimal("0"):
        logger.info("Webhook ignored because amount is zero for transaction %s", payload.transactionType.value)
        return {"status": "ignored", "transactionType": payload.transactionType.value}

    service = CashbackService(db)
    earn_points = payload.transactionType != IikoTransactionType.REFILL_WALLET_FROM_ORDER
    transaction = service.adjust_cashback_balance(
        user=user,
        amount=amount,
        branch_id=None,
        source=CashbackSource.MANUAL,
        staff_id=None,
        balance_override=balance_override,
        earn_points=earn_points,
    )
    logger.info(
        "Recorded cashback change id=%s user=%s type=%s delta=%s",
        transaction.id,
        user.id,
        payload.transactionType.value,
        amount,
    )
    return {
        "status": "processed",
        "transaction_id": transaction.id,
        "transactionType": payload.transactionType.value,
        "amount": str(amount),
    }


@router.post("/check-user")
def check_user(
    payload: IikoUserLookup,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    user = _find_user_for_identifiers(
        db, wallet_id=payload.walletId, customer_id=payload.customerId, phone=payload.phone
    )
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"id": str(user.id), "phone": user.phone, "customerId": user.iiko_customer_id}
