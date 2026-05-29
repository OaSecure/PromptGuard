from types import SimpleNamespace

from app.core.password import hash_password
from app.core.tokens import hash_refresh_token
from app.routes.auth import is_login_allowed


def test_disabled_user_cannot_login_even_with_correct_password() -> None:
    password = "correct-password"
    user = SimpleNamespace(status="DISABLED", password_hash=hash_password(password))

    assert not is_login_allowed(user, password)


def test_active_user_can_login_with_correct_password() -> None:
    password = "correct-password"
    user = SimpleNamespace(status="ACTIVE", password_hash=hash_password(password))

    assert is_login_allowed(user, password)


def test_refresh_token_hash_does_not_store_raw_token() -> None:
    raw_token = "raw-refresh-token-that-must-not-be-stored"

    token_hash = hash_refresh_token(raw_token)

    assert token_hash != raw_token
    assert raw_token not in token_hash
    assert len(token_hash) == 64
