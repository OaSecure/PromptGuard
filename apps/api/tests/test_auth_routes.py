import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.password import hash_password
from app.core.rate_limit import rate_limiter
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
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user

    def scalars(self):
        return iter([self.user])


class _RowResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.statements = []
        self.added = []

    def begin(self):
        return _SessionBegin()

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _ScalarResult(self.user)

    def add(self, item):
        self.added.append(item)


class _RefreshTokenSession(_FakeSession):
    def __init__(self, *, current_user=None, refresh_token=None):
        super().__init__(current_user)
        self.refresh_token = refresh_token

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _ScalarResult(self.refresh_token)


def _build_app(fake_session: _FakeSession, *, current_user=None) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)

    async def override_session():
        yield fake_session

    app.dependency_overrides[auth_routes.get_db_session] = override_session
    if current_user is not None:
        async def override_current_user():
            return current_user

        app.dependency_overrides[auth_routes.require_active_user] = override_current_user
    return app


def _user(status: str = "ACTIVE"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id="admin",
        login_id_normalized="admin",
        username="admin",
        email=None,
        department=None,
        display_name="PromptGuard Admin",
        role="ADMIN",
        status=status,
        password_hash=hash_password("ConfiguredAdminPassword!456"),
        last_login_at=None,
    )


def _refresh_token(*, user_id: uuid.UUID, revoked_at=None, expires_at=None, idle_expires_at=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        login_id="admin",
        token_hash="stored-hash",
        revoked_at=revoked_at,
        expires_at=expires_at or datetime(2099, 1, 1, tzinfo=timezone.utc),
        idle_expires_at=idle_expires_at or datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


def test_login_route_accepts_login_id_contract() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))

    response = client.post(
        "/auth/login",
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert fake_session.added
    assert fake_session.added[0].login_id == "admin"
    assert fake_session.added[0].idle_expires_at is not None
    assert any("login_id_normalized" in statement for statement in fake_session.statements)
    assert fake_session.user.last_login_at is not None
    assert isinstance(fake_session.user.last_login_at, datetime)


def test_login_route_rejects_disabled_user_through_route() -> None:
    fake_session = _FakeSession(_user(status="DISABLED"))
    client = TestClient(_build_app(fake_session))

    response = client.post(
        "/auth/login",
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )

    assert response.status_code == 401
    assert not fake_session.added


def test_login_route_returns_429_after_rate_limit(monkeypatch) -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post(
        "/auth/login",
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )
    second_response = client.post(
        "/auth/login",
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_login_rate_limit_does_not_trust_x_forwarded_for(monkeypatch) -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.10"},
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )
    second_response = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.11"},
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_refresh_route_returns_429_after_rate_limit(monkeypatch) -> None:
    class _RefreshSession(_FakeSession):
        async def execute(self, statement):
            self.statements.append(str(statement))
            return _RowResult(None)

    fake_session = _RefreshSession(_user())
    client = TestClient(_build_app(fake_session))
    settings = SimpleNamespace(auth_rate_limit_requests=1, auth_rate_limit_window_seconds=60)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)

    first_response = client.post("/auth/refresh", json={"refresh_token": "invalid-refresh-token"})
    second_response = client.post("/auth/refresh", json={"refresh_token": "invalid-refresh-token"})

    assert first_response.status_code == 401
    assert second_response.status_code == 429


def test_logout_requires_bearer_user_before_revoking_refresh_token() -> None:
    refresh_token = _refresh_token(user_id=uuid.uuid4())
    fake_session = _RefreshTokenSession(refresh_token=refresh_token)
    client = TestClient(_build_app(fake_session))

    response = client.post("/auth/logout", json={"refresh_token": "refresh-token"})

    assert response.status_code == 401
    assert refresh_token.revoked_at is None


def test_logout_revokes_only_current_users_refresh_token() -> None:
    current_user = _user()
    refresh_token = _refresh_token(user_id=current_user.id)
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=refresh_token)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "refresh-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert refresh_token.revoked_at is not None


def test_logout_rejects_other_users_refresh_token_without_revoking() -> None:
    current_user = _user()
    other_user_refresh = _refresh_token(user_id=uuid.uuid4())
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=other_user_refresh)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "other-user-refresh-token"})

    assert response.status_code == 401
    assert other_user_refresh.revoked_at is None


def test_logout_rejects_stale_refresh_token_without_raw_token_leak() -> None:
    current_user = _user()
    stale_refresh = _refresh_token(user_id=current_user.id, revoked_at=datetime(2026, 1, 1))
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=stale_refresh)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "stale-secret-refresh-token"})
    encoded = response.text

    assert response.status_code == 401
    assert stale_refresh.revoked_at == datetime(2026, 1, 1)
    assert "stale-secret-refresh-token" not in encoded


def test_logout_rejects_unknown_refresh_token_without_raw_token_leak() -> None:
    current_user = _user()
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=None)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "unknown-secret-refresh-token"})

    assert response.status_code == 401
    assert "unknown-secret-refresh-token" not in response.text


def test_logout_rejects_expired_refresh_token_without_revoking_again() -> None:
    current_user = _user()
    expired_refresh = _refresh_token(
        user_id=current_user.id,
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=expired_refresh)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "expired-refresh-token"})

    assert response.status_code == 401
    assert expired_refresh.revoked_at is None


def test_logout_rejects_idle_expired_refresh_token_without_revoking_again() -> None:
    current_user = _user()
    idle_expired_refresh = _refresh_token(
        user_id=current_user.id,
        idle_expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    fake_session = _RefreshTokenSession(current_user=current_user, refresh_token=idle_expired_refresh)
    client = TestClient(_build_app(fake_session, current_user=current_user))

    response = client.post("/auth/logout", json={"refresh_token": "idle-expired-refresh-token"})

    assert response.status_code == 401
    assert idle_expired_refresh.revoked_at is None
