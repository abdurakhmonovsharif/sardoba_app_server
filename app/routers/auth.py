from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_manager,
    get_current_staff,
    get_db,
    get_token_payload,
)
from app.models import AuthActorType, Staff, User
from app.schemas import (
    CashbackRead,
    ClientOTPRequest,
    ClientOTPVerify,
    RefreshRequest,
    StaffChangePasswordRequest,
    StaffCreateRequest,
    StaffLoginRequest,
    StaffRead,
    TokenResponse,
    UserRead,
)
from app.services import AuthService, CashbackService
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/client/request-otp", status_code=status.HTTP_204_NO_CONTENT)
def request_client_otp(
    payload: ClientOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        service.request_client_otp(
            phone=payload.phone,
            purpose=payload.purpose,
            ip=getattr(request.state, "ip", None),
            user_agent=getattr(request.state, "user_agent", None),
        )
    except service_exceptions.RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


@router.post("/client/verify-otp")
def verify_client_otp(
    payload: ClientOTPVerify,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    print("verify_client_otp payload:", payload.dict(exclude_none=True))
    service = AuthService(db)
    try:
        user, tokens = service.verify_client_otp(
            phone=payload.phone,
            code=payload.code,
            purpose=payload.purpose,
            name=payload.name,
            waiter_referral_code=payload.waiter_referral_code,
            date_of_birth=payload.date_of_birth,
            ip=getattr(request.state, "ip", None),
            user_agent=getattr(request.state, "user_agent", None),
        )
    except (service_exceptions.OTPExpired, service_exceptions.OTPInvalid) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    token_payload = TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"])
    print("verify_client_otp response:", token_payload.dict())
    return {"tokens": token_payload}


@router.post("/staff/login")
def staff_login(
    payload: StaffLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        staff, tokens = service.staff_login(
            phone=payload.phone,
            password=payload.password,
            ip=getattr(request.state, "ip", None),
            user_agent=getattr(request.state, "user_agent", None),
        )
    except service_exceptions.AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return {
        "staff": StaffRead.from_orm(staff),
        "tokens": TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"]),
    }


@router.post("/staff/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_staff_password(
    payload: StaffChangePasswordRequest,
    staff: Staff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        service.change_staff_password(staff=staff, old_password=payload.old_password, new_password=payload.new_password)
    except service_exceptions.AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/staff", status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreateRequest,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffRead:
    branch_id = int(payload.branch_id) if payload.branch_id is not None else None
    service = AuthService(db)
    try:
        staff = service.create_staff(
            name=payload.name,
            phone=payload.phone,
            password=payload.password,
            role=payload.role,
            branch_id=branch_id,
            actor=manager,
        )
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return StaffRead.from_orm(staff)


@router.post("/refresh")
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not payload.refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token is required")
    service = AuthService(db)
    try:
        tokens = service.refresh_tokens(refresh_token=payload.refresh_token)
    except service_exceptions.AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"])


@router.get("/me")
def read_profile(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
    cashback_limit: int = 10,
):
    actor_type = payload.get("actor_type")
    subject_raw = payload.get("sub")
    if subject_raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    subject = int(subject_raw)

    if actor_type == AuthActorType.CLIENT.value:
        user = db.query(User).filter(User.id == subject).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        cashback_service = CashbackService(db)
        transactions = cashback_service.get_user_cashbacks(user_id=user.id, limit=cashback_limit)
        loyalty = cashback_service.loyalty_summary(user=user)
        return {
            "type": AuthActorType.CLIENT.value,
            "profile": UserRead.from_orm(user),
            "cashback": {
                "balance": loyalty["current_points"],
                "transactions": [CashbackRead.from_orm(entry) for entry in transactions],
                "currency": "UZS",
                "loyalty": loyalty,
            },
        }

    if actor_type == AuthActorType.STAFF.value:
        staff = db.query(Staff).filter(Staff.id == subject).first()
        if not staff:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
        return {"type": AuthActorType.STAFF.value, "profile": StaffRead.from_orm(staff)}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown actor type")
