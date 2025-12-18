import logging
import traceback
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models import CashbackSource, User
from app.schemas import IikoTransactionType, IikoWebhookPayload
from app.services import CashbackService
from app.schemas.iiko import IikoUserLookup

router = APIRouter(prefix="/iiko", tags=["iiko"])
logger = logging.getLogger("iiko.webhook")

_MAX_LOG_BODY_CHARS = 5000


def _truncate_body(body: str) -> str:
    if not body:
        return body
    if len(body) <= _MAX_LOG_BODY_CHARS:
        return body
    return body[:_MAX_LOG_BODY_CHARS] + f"... <truncated {len(body) - _MAX_LOG_BODY_CHARS} chars>"


def _report_webhook_error(*, message: str, body_text: str, exc: Exception | None = None) -> None:
    safe_body = _truncate_body(body_text)
    if exc is None:
        logger.error("%s | body=%s", message, safe_body)
        print(f"[iiko.webhook] {message} | body={safe_body}")
        return
    logger.exception("%s | body=%s", message, safe_body)
    print(f"[iiko.webhook] {message} | body={safe_body}")
    traceback.print_exc()


def _determine_amount(payload: IikoWebhookPayload) -> Decimal:
    raw = payload.sum
    if payload.transactionType == IikoTransactionType.ACCRUAL:
        return abs(raw)
    if payload.transactionType == IikoTransactionType.PAY_FROM_WALLET:
        return -abs(raw)
    return raw


def _find_user_for_identifiers(
    db: Session, *, wallet_id: str, customer_id: str, phone: str
) -> User | None:

    return (
        db.query(User)
        .filter(
            User.iiko_wallet_id == wallet_id,
            User.iiko_customer_id == customer_id,
            User.phone == phone,
            User.is_deleted == False,
        )
        .first()
    )


@router.post("/webhook")
async def iiko_webhook(
    request: Request, db: Session = Depends(get_db)
) -> dict[str, str | int]:
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
    logger.info("Incoming iiko webhook body: %s", _truncate_body(body_text))

    try:
        if not body_text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Request body is empty")

        try:
            payload = IikoWebhookPayload.parse_raw(body_text)
        except ValidationError as exc:
            logger.warning("Invalid iiko webhook payload: %s", exc)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload"
            ) from exc

        if not payload.walletId and not payload.customerId:
            logger.warning(
                "Webhook missing identifiers; body=%s",
                _truncate_body(body_text),
            )
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="walletId or customerId is required to locate the user",
            )
        user = _find_user_for_identifiers(
            db,
            wallet_id=payload.walletId,
            customer_id=payload.customerId,
            phone=payload.phone,
        )
        if not user:
            logger.warning(
                "User not found for webhook; walletId=%s customerId=%s body=%s",
                payload.walletId,
                payload.customerId,
                _truncate_body(body_text),
            )
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

        amount = _determine_amount(payload)
        balance_override = None
        if payload.balance is not None:
            balance_override = Decimal(str(payload.balance))
        if amount == Decimal("0"):
            logger.info(
                "Webhook ignored because amount is zero for transaction %s",
                payload.transactionType.value,
            )
            return {"status": "ignored", "transactionType": payload.transactionType.value}

        service = CashbackService(db)
        earn_points = (
            payload.transactionType != IikoTransactionType.REFILL_WALLET_FROM_ORDER
        )
        transaction = service.adjust_cashback_balance(
            user=user,
            amount=amount,
            branch_id=None,
            source=CashbackSource.MANUAL,
            staff_id=None,
            event_id=payload.id,
            uoc_id=payload.uocId,
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
    except HTTPException as exc:
        _report_webhook_error(
            message=f"IIKO webhook rejected ({exc.status_code}): {exc.detail}",
            body_text=body_text,
        )
        raise
    except Exception as exc:
        _report_webhook_error(message="Unhandled error in IIKO webhook", body_text=body_text, exc=exc)
        raise


@router.post("/check-user")
def check_user(
    payload: IikoUserLookup,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    try:
        user = _find_user_for_identifiers(
            db,
            wallet_id=payload.walletId,
            customer_id=payload.customerId,
            phone=payload.phone,
        )
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
        return {
            "id": str(user.id),
            "phone": user.phone,
            "customerId": user.iiko_customer_id,
        }
    except HTTPException as exc:
        _report_webhook_error(
            message=f"IIKO check-user rejected ({exc.status_code}): {exc.detail}",
            body_text=payload.json(),
        )
        raise
    except Exception as exc:
        _report_webhook_error(message="Unhandled error in IIKO check-user", body_text=payload.json(), exc=exc)
        raise
