from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from passlib.context import CryptContext

from .config import get_settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_password_hash(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_context.verify(password, hashed_password)


def create_access_token(
    *,
    subject: str | int,
    token_type: str,
    additional_claims: Dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "exp": expire,
    }
    if additional_claims:
        payload.update(additional_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def create_refresh_token(
    *,
    subject: str | int,
    token_type: str,
    additional_claims: Dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(tz=timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "exp": expire,
        "scope": "refresh",
    }
    if additional_claims:
        payload.update(additional_claims)
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])


def decode_refresh_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_REFRESH_SECRET_KEY, algorithms=["HS256"])
