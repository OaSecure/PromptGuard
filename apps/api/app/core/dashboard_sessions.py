import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.tokens import utc_now

DASHBOARD_SESSION_COOKIE = "pg_dashboard_session"
DASHBOARD_CSRF_COOKIE = "pg_dashboard_csrf"
DASHBOARD_CSRF_HEADER = "X-CSRF-Token"


def create_dashboard_session_token() -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_dashboard_session_token(raw_token), dashboard_session_expires_at()


def create_csrf_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_dashboard_csrf_token(raw_token)


def dashboard_session_expires_at() -> datetime:
    return utc_now() + timedelta(hours=get_settings().dashboard_session_ttl_hours)


def hash_dashboard_session_token(raw_token: str) -> str:
    return _hash_with_dashboard_secret("dashboard-session", raw_token)


def hash_dashboard_csrf_token(raw_token: str) -> str:
    return _hash_with_dashboard_secret("dashboard-csrf", raw_token)


def verify_csrf_token(raw_token: str | None, expected_hash: str | None) -> bool:
    if not raw_token or not expected_hash:
        return False
    return hmac.compare_digest(hash_dashboard_csrf_token(raw_token), expected_hash)


def _hash_with_dashboard_secret(scope: str, raw_token: str) -> str:
    secret = get_settings().dashboard_session_secret.encode("utf-8")
    message = f"{scope}:{raw_token}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()
