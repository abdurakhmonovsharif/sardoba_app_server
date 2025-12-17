from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db, get_token_payload
from app.core.localization import localize_message
from app.models import AuthActorType, Staff, User, CashbackTransaction, SardobaBranch
from app.schemas import (
    CashbackCreate,
    CashbackHistoryResponse,
    CashbackRead,
    CashbackUseRequest,
    CashbackUseResponse,
    TopUserLeaderboardRow,
    LoyaltyAnalytics,
    LoyaltySummary,
    WaiterLeaderboardRow,
)
from app.services import CashbackService
from app.services import exceptions as service_exceptions
from typing import Optional

router = APIRouter(prefix="/cashback", tags=["cashback"])

@router.post("/add", response_model=CashbackRead)
def add_cashback(
    payload: CashbackCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CashbackService(db)
    branch_id = int(payload.branch_id) if payload.branch_id is not None else None
    cashback = service.add_cashback(
        actor=manager,
        user_id=payload.user_id,
        amount=payload.amount,
        branch_id=branch_id,
        source=payload.source,
    )
    return CashbackRead.from_orm(cashback)


@router.post("/use", response_model=CashbackUseResponse)
def use_cashback(
    payload: CashbackUseRequest,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> CashbackUseResponse:
    service = CashbackService(db)
    try:
        balance = service.check_cashback_payment(user_id=payload.user_id, amount=payload.amount)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    except service_exceptions.ServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message(str(exc))) from exc
    return CashbackUseResponse(
        can_use_cashback=True,
        balance=balance,
        message=localize_message("Cashback payment is available."),
    )


@router.get("/user/{user_id}", response_model=CashbackHistoryResponse)
def get_user_cashback(
    user_id: int,
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
):
    actor_type = payload.get("actor_type")
    subject_raw = payload.get("sub")
    if subject_raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Invalid token"))
    subject_id = int(subject_raw)

    if actor_type == AuthActorType.CLIENT.value and subject_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=localize_message("Forbidden"))

    if actor_type == AuthActorType.STAFF.value:
        staff = db.query(Staff).filter(Staff.id == subject_id).first()
        if not staff:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Staff not found"))
    elif actor_type != AuthActorType.CLIENT.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=localize_message("Forbidden"))

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("User not found"))

    service = CashbackService(db)
    entries = service.get_user_cashbacks(user_id=user.id)
    loyalty = service.loyalty_summary(user=user)
    return {
        "loyalty": loyalty,
        "transactions": [CashbackRead.from_orm(entry) for entry in entries],
    }



@router.get("/loyalty-analytics", response_model=LoyaltyAnalytics)
def loyalty_analytics(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    """Return aggregated cashback analytics (levels disabled temporarily)."""
    service = CashbackService(db)
    return service.loyalty_analytics_summary()


@router.get("/waiter-stats", response_model=list[WaiterLeaderboardRow])
def waiter_leaderboard(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CashbackService(db)
    rows = service.waiter_leaderboard()
    return [WaiterLeaderboardRow(**row) for row in rows]


@router.get("/top-users", response_model=list[TopUserLeaderboardRow])
def top_users_leaderboard(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=50),
):
    service = CashbackService(db)
    rows = service.top_users_leaderboard(limit=limit)
    return [TopUserLeaderboardRow(**row) for row in rows]



@router.get("", response_model=dict)
def list_cashbacks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str = Query(default=""),
    branch: Optional[SardobaBranch] = Query(default=None),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    """List cashback transactions (admin/manager only). Supports optional search by user name/phone and branch filter."""
    query = db.query(CashbackTransaction).join(User).order_by(CashbackTransaction.created_at.desc())

    if branch is not None:
        # branch may be an Enum; compare to stored value
        try:
            branch_value = branch.value if hasattr(branch, "value") else int(branch)
        except Exception:
            branch_value = branch
        query = query.filter(CashbackTransaction.branch_id == branch_value)

    if search:
        term = f"%{search}%"
        query = query.filter((User.name.ilike(term)) | (User.phone.ilike(term)))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "pagination": {"page": page, "size": page_size, "total": total},
        "items": [CashbackRead.from_orm(i) for i in items],
    }
