import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.password import hash_password
from app.core.rate_limit import rate_limiter
from app.core.tokens import create_access_token, create_refresh_token, hash_refresh_token, utc_now
from app.models.auth import RefreshToken, User
from app.routes import auth as auth_routes


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


class _SessionBegin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _ScalarResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        return self.item

    def scalars(self):
        return iter([])


class _RowResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _FakeSession:
    def __init__(self, users=None, refresh_tokens=None):
        self.users = users or []
        self.refresh_tokens = refresh_tokens or []
        self.statements = []
        self.added = []
        self.commits = 0
        self.flushed = 0

    def begin(self):
        return _SessionBegin()

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "JOIN users" in statement_text:
            token_hash = _where_value(statement, "token_hash")
            refresh_token = next((item for item in self.refresh_tokens if item.token_hash == token_hash), None)
            user = next((item for item in self.users if refresh_token is not None and item.id == refresh_token.user_id), None)
            return _RowResult((refresh_token, user) if refresh_token is not None and user is not None else None)
        if "FROM refresh_tokens" in statement_text:
            token_hash = _where_value(statement, "token_hash")
            refresh_token = next((item for item in self.refresh_tokens if item.token_hash == token_hash), None)
            return _ScalarResult(refresh_token)
        if "login_id_normalized" in statement_text:
            login_id = _where_value(statement, "login_id_normalized")
            user = next((item for item in self.users if item.login_id_normalized == login_id), None)
            return _ScalarResult(user)
        return _ScalarResult(None)

    async def get(self, model, item_id):
        if model is User:
            return next((item for item in self.users if item.id == item_id), None)
        return None

    def add(self, item):
        self.added.append(item)
        if isinstance(item, RefreshToken):
            self.refresh_tokens.append(item)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1


def _where_value(statement, field_name: str):
    for criteria in getattr(statement, "_where_criteria", ()):
        left = getattr(criteria, "left", None)
        if getattr(left, "name", None) == field_name:
            return getattr(criteria.right, "value", None)
    return None


def _build_app(fake_session: _FakeSession) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)

    async def override_session():
        yield fake_session

    app.dependency_overrides[auth_routes.get_db_session] = override_session
    return app


def _user(*, status: str = "ACTIVE", role: str = "ADMIN", password: str = "ConfiguredAdminPassword!456"):
    login_id = f"admin-{uuid.uuid4().hex[:8]}"
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id=login_id,
        login_id_normalized=login_id.casefold(),
        username=login_id,
        email=None,
        department="Security",
        display_name="PromptGuard Admin",
        role=role,
        status=status,
        password_hash=hash_password(password),
        last_login_at=None,
    )


def _auth_header(user_id: uuid.UUID) -> dict[str, str]:
    access_token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {access_token}"}


def _refresh_token_for(user_id: uuid.UUID, raw_token: str | None = None, **overrides) -> tuple[str, RefreshToken]:
    if raw_token is None:
        raw_token, token_hash, expires_at = create_refresh_token()
    else:
        token_hash = hash_refresh_token(raw_token)
        expires_at = utc_now() + timedelta(days=30)
    values = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "login_id": None,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "idle_expires_at": None,
        "revoked_at": None,
        "replaced_by_token_id": None,
    }
    values.update(overrides)
    return raw_token, RefreshToken(**values)


def test_login_route_accepts_login_id_contract_and_stores_only_refresh_hash() -> None:
    password = "ConfiguredAdminPassword!456"
    user = _user(password=password)
    fake_session = _FakeSession(users=[user])
    client = TestClient(_build_app(fake_session))

    before = utc_now()
    response = client.post(
        "/auth/login",
        json={"login_id": user.login_id, "password": password},
    )
    after = utc_now()
    body = response.json()
    created_refresh = next(item for item in fake_session.added if isinstance(item, RefreshToken))

    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert created_refresh.token_hash == hash_refresh_token(body["refresh_token"])
    assert created_refresh.token_hash != body["refresh_token"]
    assert created_refresh.login_id == user.login_id
    assert created_refresh.idle_expires_at is not None
    assert body["refresh_token"] not in json.dumps(created_refresh.__dict__, default=str)
    assert any("login_id_normalized" in statement for statement in fake_session.statements)
    assert user.last_login_at is not None
    assert before <= user.last_login_at <= after


def test_login_route_uses_default_access_and_refresh_ttl() -> None:
    user = _user()
    fake_session = _FakeSession(users=[user])
    client = TestClient(_build_app(fake_session))

    before = utc_now()
    response = client.post(
        "/auth/login",
        json={"login_id": user.login_id, "password": "ConfiguredAdminPassword!456"},
    )
    after = utc_now()
    body = response.json()
    created_refresh = next(item for item in fake_session.added if isinstance(item, RefreshToken))
    access_expires_at = datetime.fromisoformat(body["access_token_expires_at"])

    assert response.status_code == 200
    assert before + timedelta(minutes=14, seconds=50) <= access_expires_at <= after + timedelta(minutes=15, seconds=10)
    assert before + timedelta(days=29, hours=23, minutes=59) <= created_refresh.expires_at <= after + timedelta(days=30, minutes=1)
    assert before + timedelta(days=13, hours=23, minutes=59) <= created_refresh.idle_expires_at <= after + timedelta(days=14, minutes=1)


def test_login_route_rejects_missing_bad_password_and_disabled_user_the_same_way() -> None:
    password = "ConfiguredAdminPassword!456"
    active_user = _user(password=password)
    disabled_user = _user(status="DISABLED", password=password)

    missing_response = TestClient(_build_app(_FakeSession(users=[]))).post(
        "/auth/login",
        json={"login_id": "missing", "password": password},
    )
    bad_password_response = TestClient(_build_app(_FakeSession(users=[active_user]))).post(
        "/auth/login",
        json={"login_id": active_user.login_id, "password": "wrong-password"},
    )
    disabled_response = TestClient(_build_app(_FakeSession(users=[disabled_user]))).post(
        "/auth/login",
        json={"login_id": disabled_user.login_id, "password": password},
    )

    assert missing_response.status_code == 401
    assert bad_password_response.status_code == 401
    assert disabled_response.status_code == 401
    assert missing_response.json() == bad_password_response.json() == disabled_response.json()


def test_refresh_rotates_token_and_stores_only_new_hash() -> None:
    user = _user()
    raw_refresh, refresh_token = _refresh_token_for(user.id)
    fake_session = _FakeSession(users=[user], refresh_tokens=[refresh_token])
    client = TestClient(_build_app(fake_session))

    response = client.post("/auth/refresh", json={"refresh_token": raw_refresh})
    body = response.json()
    new_refresh = next(item for item in fake_session.added if isinstance(item, RefreshToken) and item is not refresh_token)

    assert response.status_code == 200
    assert body["access_token"]
    assert body["refresh_token"] != raw_refresh
    assert refresh_token.revoked_at is not None
    assert refresh_token.replaced_by_token_id == new_refresh.id
    assert new_refresh.login_id == user.login_id
    assert new_refresh.idle_expires_at is not None
    assert new_refresh.token_hash == hash_refresh_token(body["refresh_token"])
    assert new_refresh.token_hash != body["refresh_token"]
    assert body["refresh_token"] not in json.dumps(new_refresh.__dict__, default=str)
    assert fake_session.flushed == 1


def test_refresh_rejects_revoked_or_expired_token_with_401() -> None:
    user = _user()
    revoked_raw, revoked_token = _refresh_token_for(user.id, revoked_at=utc_now())
    expired_raw, expired_token = _refresh_token_for(user.id, expires_at=utc_now() - timedelta(seconds=1))

    revoked_response = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[revoked_token]))).post(
        "/auth/refresh",
        json={"refresh_token": revoked_raw},
    )
    expired_response = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[expired_token]))).post(
        "/auth/refresh",
        json={"refresh_token": expired_raw},
    )

    assert revoked_response.status_code == 401
    assert expired_response.status_code == 401


def test_refresh_rejects_idle_expired_token_with_401() -> None:
    user = _user()
    idle_expired_raw, idle_expired_token = _refresh_token_for(
        user.id,
        idle_expires_at=utc_now() - timedelta(seconds=1),
    )

    response = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[idle_expired_token]))).post(
        "/auth/refresh",
        json={"refresh_token": idle_expired_raw},
    )

    assert response.status_code == 401


def test_refresh_allows_legacy_token_without_idle_expiry_and_rotates_to_idle_expiry() -> None:
    user = _user()
    raw_refresh, refresh_token = _refresh_token_for(user.id, idle_expires_at=None)
    fake_session = _FakeSession(users=[user], refresh_tokens=[refresh_token])

    response = TestClient(_build_app(fake_session)).post("/auth/refresh", json={"refresh_token": raw_refresh})
    new_refresh = next(item for item in fake_session.added if isinstance(item, RefreshToken) and item is not refresh_token)

    assert response.status_code == 200
    assert new_refresh.login_id == user.login_id
    assert new_refresh.idle_expires_at is not None


def test_refresh_rejects_disabled_user_existing_refresh_token_with_403() -> None:
    user = _user(status="DISABLED")
    raw_refresh, refresh_token = _refresh_token_for(user.id)
    response = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[refresh_token]))).post(
        "/auth/refresh",
        json={"refresh_token": raw_refresh},
    )

    assert response.status_code == 403
    assert refresh_token.revoked_at is None


def test_refresh_idle_timeout_schema_metadata_exists() -> None:
    assert hasattr(RefreshToken, "idle_expires_at")


def test_me_returns_safe_user_metadata_only() -> None:
    user = _user()
    user.last_login_at = utc_now()
    response = TestClient(_build_app(_FakeSession(users=[user]))).get("/auth/me", headers=_auth_header(user.id))
    body = response.json()
    encoded = json.dumps(body)

    assert response.status_code == 200
    assert set(body) == {"login_id", "username", "department", "display_name", "role", "status", "last_login_at"}
    assert body["login_id"] == user.login_id
    assert "password" not in encoded
    assert "password_hash" not in encoded
    assert "token_hash" not in encoded
    assert "refresh_token" not in encoded
    assert "access_token" not in encoded
    assert "session" not in encoded.casefold()


def test_me_and_logout_require_bearer_token() -> None:
    user = _user()
    raw_refresh, refresh_token = _refresh_token_for(user.id)
    client = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[refresh_token])))

    me_response = client.get("/auth/me")
    logout_response = client.post("/auth/logout", json={"refresh_token": raw_refresh})

    assert me_response.status_code == 401
    assert logout_response.status_code == 401
    assert refresh_token.revoked_at is None


def test_disabled_user_existing_access_token_is_forbidden_for_me_and_logout() -> None:
    user = _user(status="DISABLED")
    raw_refresh, refresh_token = _refresh_token_for(user.id)
    client = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[refresh_token])))

    me_response = client.get("/auth/me", headers=_auth_header(user.id))
    logout_response = client.post("/auth/logout", headers=_auth_header(user.id), json={"refresh_token": raw_refresh})

    assert me_response.status_code == 403
    assert logout_response.status_code == 403
    assert refresh_token.revoked_at is None


def test_logout_revokes_only_current_users_refresh_token() -> None:
    current_user = _user()
    other_user = _user()
    current_raw, current_token = _refresh_token_for(current_user.id)
    other_raw, other_token = _refresh_token_for(other_user.id)
    client = TestClient(_build_app(_FakeSession(users=[current_user, other_user], refresh_tokens=[current_token, other_token])))

    other_response = client.post("/auth/logout", headers=_auth_header(current_user.id), json={"refresh_token": other_raw})
    current_response = client.post("/auth/logout", headers=_auth_header(current_user.id), json={"refresh_token": current_raw})

    assert other_response.status_code == 200
    assert other_response.json() == {"ok": True}
    assert other_token.revoked_at is None
    assert current_response.status_code == 200
    assert current_token.revoked_at is not None


def test_logout_is_idempotent_for_missing_and_already_revoked_refresh_token() -> None:
    user = _user()
    raw_refresh, refresh_token = _refresh_token_for(user.id, revoked_at=utc_now())
    client = TestClient(_build_app(_FakeSession(users=[user], refresh_tokens=[refresh_token])))

    missing_response = client.post(
        "/auth/logout",
        headers=_auth_header(user.id),
        json={"refresh_token": "not-present-refresh-token"},
    )
    revoked_response = client.post(
        "/auth/logout",
        headers=_auth_header(user.id),
        json={"refresh_token": raw_refresh},
    )

    assert missing_response.status_code == 200
    assert revoked_response.status_code == 200
    assert missing_response.json() == {"ok": True}
    assert revoked_response.json() == {"ok": True}


def test_login_route_returns_429_after_rate_limit(monkeypatch) -> None:
    user = _user()
    fake_session = _FakeSession(users=[user])
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post(
        "/auth/login",
        json={"login_id": user.login_id, "password": "ConfiguredAdminPassword!456"},
    )
    second_response = client.post(
        "/auth/login",
        json={"login_id": user.login_id, "password": "ConfiguredAdminPassword!456"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_login_rate_limit_does_not_trust_x_forwarded_for(monkeypatch) -> None:
    user = _user()
    fake_session = _FakeSession(users=[user])
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.10"},
        json={"login_id": user.login_id, "password": "ConfiguredAdminPassword!456"},
    )
    second_response = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.11"},
        json={"login_id": user.login_id, "password": "ConfiguredAdminPassword!456"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_refresh_route_returns_429_after_rate_limit(monkeypatch) -> None:
    user = _user()
    fake_session = _FakeSession(users=[user])
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post("/auth/refresh", json={"refresh_token": "invalid-refresh-token"})
    second_response = client.post("/auth/refresh", json={"refresh_token": "invalid-refresh-token"})

    assert first_response.status_code == 401
    assert second_response.status_code == 429
