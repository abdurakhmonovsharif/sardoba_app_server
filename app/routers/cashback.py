from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db, get_token_payload
from app.models import AuthActorType, Staff, User
from app.schemas import CashbackCreate, CashbackHistoryResponse, CashbackRead
from app.services import CashbackService

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


@router.get("/user/{user_id}", response_model=CashbackHistoryResponse)
def get_user_cashback(
    user_id: int,
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
):
    actor_type = payload.get("actor_type")
    subject_raw = payload.get("sub")
    if subject_raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    subject_id = int(subject_raw)

    if actor_type == AuthActorType.CLIENT.value and subject_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if actor_type == AuthActorType.STAFF.value:
        staff = db.query(Staff).filter(Staff.id == subject_id).first()
        if not staff:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff not found")
    elif actor_type != AuthActorType.CLIENT.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    service = CashbackService(db)
    entries = service.get_user_cashbacks(user_id=user.id)
    loyalty = service.loyalty_summary(user=user)
    return {
        "loyalty": loyalty,
        "transactions": [CashbackRead.from_orm(entry) for entry in entries],
    }
