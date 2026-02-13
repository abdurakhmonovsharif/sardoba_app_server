from datetime import datetime, timezone
from decimal import Decimal
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy.orm import Session

from app.core.cache import RedisCacheBackend, cache_manager
from app.core.phone import normalize_uzbek_phone
from app.core.dependencies import (
    get_current_manager,
    get_current_staff,
    get_db,
    get_token_payload,
)
from app.core.localization import localize_message
from app.models import AuthActorType, Card, Staff, User
from app.schemas import (
    CashbackRead,
    CardRead,
    ClientOTPRequest,
    ClientOTPVerify,
    RefreshRequest,
    StaffChangePasswordRequest,
    StaffCreateRequest,
    StaffLoginRequest,
    StaffRead,
    StaffListResponse,
    TokenResponse,
    UserRead,
)
from app.services import AuthService, CashbackService, IikoSyncJobService, StaffService
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)
_FALLBACK_DEMO_PHONE = "+998911111111"
_SYNC_RATE_LIMIT_SECONDS = 300  # 5 minutes


@router.post("/client/request-otp", status_code=status.HTTP_204_NO_CONTENT)
def request_client_otp(
    payload: ClientOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    phone = normalize_uzbek_phone(payload.phone)
    service = AuthService(db)
    try:
        service.request_client_otp(
            phone=phone,
            purpose=payload.purpose,
            ip=getattr(request.state, "ip", None),
            user_agent=getattr(request.state, "user_agent", None),
        )
    except service_exceptions.RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=localize_message(str(exc)),
        ) from exc
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc
    except service_exceptions.OTPDeliveryFailed as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=localize_message(str(exc))) from exc


@router.post("/client/verify-otp")
def verify_client_otp(
    payload: ClientOTPVerify,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    phone = normalize_uzbek_phone(payload.phone)
    service = AuthService(db)
    try:
        user, tokens = service.verify_client_otp(
            phone=phone,
            code=payload.code,
            purpose=payload.purpose,
            name=payload.name,
            waiter_referral_code=payload.waiter_referral_code,
            date_of_birth=payload.date_of_birth,
            ip=getattr(request.state, "ip", None),
            user_agent=getattr(request.state, "user_agent", None),
        )
    except (service_exceptions.OTPExpired, service_exceptions.OTPInvalid) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message(str(exc))) from exc
    except service_exceptions.ExternalServiceBadRequest as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message(str(exc))) from exc
    except service_exceptions.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message(str(exc))) from exc
    except service_exceptions.ServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=localize_message(str(exc))) from exc

    _enqueue_user_sync_job(
        db,
        user_id=user.id,
        phone=user.phone,
        create_if_missing=True,
        source="auth_verify_otp",
    )

    token_payload = TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"])
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message(str(exc))) from exc
    except service_exceptions.RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=localize_message(str(exc))) from exc

    response: dict = {
        "staff": StaffRead.from_orm(staff),
        "tokens": TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"]),
    }
    if staff.role.name == "WAITER":
        clients = (
            db.query(User)
            .filter(User.waiter_id == staff.id, User.is_deleted == False)  # noqa: E712
            .order_by(User.created_at.desc())
            .all()
        )
        response["clients"] = [UserRead.from_orm(user) for user in clients]
    return response


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message(str(exc))) from exc


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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=localize_message(str(exc))) from exc

    return StaffRead.from_orm(staff)


@router.get("/staff", response_model=StaffListResponse)
def list_staff(
    search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> StaffListResponse:
    service = StaffService(db)
    total, staff_members = service.list_staff(page=page, size=size, search=search)
    return StaffListResponse(
        pagination={"page": page, "size": size, "total": total},
        items=[StaffRead.from_orm(member) for member in staff_members],
    )


@router.post("/refresh")
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not payload.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("refresh_token is required")
        )
    service = AuthService(db)
    try:
        tokens = service.refresh_tokens(refresh_token=payload.refresh_token)
    except service_exceptions.AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message(str(exc))) from exc
    return TokenResponse(access_token=tokens["access"], refresh_token=tokens["refresh"])


def _enqueue_user_sync_job(
    db: Session,
    *,
    user_id: int,
    phone: str,
    create_if_missing: bool,
    source: str,
) -> None:
    try:
        IikoSyncJobService(db).enqueue_user_sync(
            user_id=user_id,
            phone=phone,
            create_if_missing=create_if_missing,
            source=source,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to enqueue Iiko sync job for user %s", user_id)


def _should_rate_limit_sync(user_id: int) -> bool:
    backend = cache_manager.get_backend()
    if not isinstance(backend, RedisCacheBackend) or backend.client is None:
        logger.info("skip_sync_no_redis", extra={"user_id": user_id})
        return True

    key = f"iiko:sync:last:{user_id}"
    try:
        allowed = backend.client.set(key, "1", nx=True, ex=_SYNC_RATE_LIMIT_SECONDS)
        return not bool(allowed)
    except Exception:
        logger.warning("skip_sync_redis_error", extra={"user_id": user_id})
        return True


@router.get("/me")
def read_profile(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
    cashback_limit: int = 10,
):
    actor_type = payload.get("actor_type") or payload.get("type")
    if actor_type == AuthActorType.CLIENT.value and payload.get("mock_user"):
        now = datetime.now(tz=timezone.utc)
        phone = payload.get("phone") or _FALLBACK_DEMO_PHONE
        balance = Decimal("0.00")
        return {
            "type": AuthActorType.CLIENT.value,
            "profile": {
                "id": 0,
                "name": "Test User",
                "phone": phone,
                "waiter_id": None,
                "date_of_birth": None,
                "profile_photo_url": None,
                "cashback_balance": balance,
                "email": None,
                "gender": None,
                "surname": None,
                "middleName": None,
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            },
            "cashback": {
                "balance": balance,
                "transactions": [],
                "cards": [],
                "currency": "UZS",
                "loyalty": {"cashback_balance": balance},
            },
        }
    subject_raw = payload.get("sub")
    if subject_raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=localize_message("Invalid token"))
    subject = int(subject_raw)

    if actor_type == AuthActorType.CLIENT.value:
        user = db.query(User).filter(User.id == subject).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("User not found"))
        cashback_service = CashbackService(db)
        transactions = cashback_service.get_user_cashbacks(user_id=user.id, limit=cashback_limit)
        loyalty = cashback_service.loyalty_summary(user=user)

        # Fire-and-forget optional sync; request path only writes a local queue row.
        if not user.is_deleted and user.iiko_customer_id and not _should_rate_limit_sync(user.id):
            _enqueue_user_sync_job(
                db,
                user_id=user.id,
                phone=user.phone,
                create_if_missing=False,
                source="auth_me_refresh",
            )

        return {
            "type": AuthActorType.CLIENT.value,
            "profile": UserRead.from_orm(user),
            "cashback": {
                "balance": loyalty["cashback_balance"],
                "transactions": [CashbackRead.from_orm(entry) for entry in transactions],
                "cards": [CardRead.from_orm(card) for card in db.query(Card).filter(Card.user_id == user.id).all()],
                "currency": "UZS",
                "loyalty": loyalty,
            },
        }

    if actor_type == AuthActorType.STAFF.value:
        staff = db.query(Staff).filter(Staff.id == subject).first()
        if not staff:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("Staff not found"))
        payload = {"type": AuthActorType.STAFF.value, "profile": StaffRead.from_orm(staff)}
        if staff.role.name == "WAITER":
            clients = (
                db.query(User)
                .filter(User.waiter_id == staff.id, User.is_deleted == False)  # noqa: E712
                .order_by(User.created_at.desc())
                .all()
            )
            payload["clients"] = [UserRead.from_orm(user) for user in clients]
        return payload

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Unknown actor type"))
