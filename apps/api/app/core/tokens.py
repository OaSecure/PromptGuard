import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings

ACCESS_TOKEN_TYPE = "access"


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = utc_now() + timedelta(minutes=settings.access_token_expires_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": ACCESS_TOKEN_TYPE,
        "exp": expires_at,
        "iat": utc_now(),
    }
    token = jwt.encode(payload, settings.access_token_secret, algorithm="HS256")
    return token, expires_at


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, get_settings().access_token_secret, algorithms=["HS256"])
    except InvalidTokenError:
        return None

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None

    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def create_refresh_token() -> tuple[str, str, datetime]:
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_refresh_token(raw_token)
    expires_at = utc_now() + timedelta(days=settings.refresh_token_expires_days)
    return raw_token, token_hash, expires_at


def hash_refresh_token(raw_token: str) -> str:
    return hmac.new(
        get_settings().refresh_token_secret.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
