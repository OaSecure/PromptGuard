import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.dashboard_sessions import (
    DASHBOARD_CSRF_HEADER,
    DASHBOARD_SESSION_COOKIE,
    hash_dashboard_session_token,
)
from app.core.password import hash_password
from app.core.rate_limit import rate_limiter
from app.core.tokens import utc_now
from app.models.auth import DashboardSession
from app.routes import dashboard_session


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


class _RowResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.added = []
        self.commits = 0

    def begin(self):
        return _SessionBegin()

    async def execute(self, statement):
        statement_text = str(statement)
        if "dashboard_sessions" in statement_text:
            session_hash = self.added[-1].session_hash if self.added else ""
            return _RowResult((self.added[-1], self.user) if self.added and self.added[-1].session_hash == session_hash else None)
        return _ScalarResult(self.user)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


def _user(*, role: str = "ADMIN", status: str = "ACTIVE"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id="admin" if role == "ADMIN" else "member",
        login_id_normalized="admin" if role == "ADMIN" else "member",
        username="admin" if role == "ADMIN" else "member",
        email=None,
        department="Security",
        display_name="PromptGuard Admin",
        role=role,
        status=status,
        password_hash=hash_password("ConfiguredAdminPassword!456"),
        last_login_at=None,
    )


def _build_app(fake_session: _FakeSession) -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_session.router)

    async def override_session():
        yield fake_session

    app.dependency_overrides[dashboard_session.get_db_session] = override_session
    return app


def _csrf(client: TestClient) -> str:
    response = client.get("/dashboard/session/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _login(client: TestClient, csrf_token: str):
    return client.post(
        "/dashboard/session/login",
        headers={DASHBOARD_CSRF_HEADER: csrf_token},
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )


def test_dashboard_csrf_endpoint_sets_safe_cookie_and_returns_token() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))

    response = client.get("/dashboard/session/csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "pg_dashboard_csrf" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_dashboard_admin_login_creates_hash_only_session_cookie() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))
    csrf_token = _csrf(client)

    response = _login(client, csrf_token)

    assert response.status_code == 200
    assert response.json() == {
        "login_id": "admin",
        "username": "admin",
        "department": "Security",
        "role": "ADMIN",
        "status": "ACTIVE",
    }
    assert "httponly" in response.headers["set-cookie"].lower()
    assert DASHBOARD_SESSION_COOKIE in response.headers["set-cookie"]
    assert fake_session.added
    assert isinstance(fake_session.added[0], DashboardSession)
    assert fake_session.added[0].session_hash
    assert fake_session.added[0].session_hash != client.cookies.get(DASHBOARD_SESSION_COOKIE)
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert "session_hash" not in response.text
    assert "refresh_token" not in response.text


def test_dashboard_user_login_is_forbidden() -> None:
    fake_session = _FakeSession(_user(role="USER"))
    client = TestClient(_build_app(fake_session))
    csrf_token = _csrf(client)

    response = _login(client, csrf_token)

    assert response.status_code == 403
    assert not fake_session.added


def test_dashboard_disabled_user_login_fails() -> None:
    fake_session = _FakeSession(_user(status="DISABLED"))
    client = TestClient(_build_app(fake_session))
    csrf_token = _csrf(client)

    response = _login(client, csrf_token)

    assert response.status_code == 401
    assert not fake_session.added


def test_dashboard_login_requires_csrf() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))

    response = client.post(
        "/dashboard/session/login",
        json={"login_id": "admin", "password": "ConfiguredAdminPassword!456"},
    )

    assert response.status_code == 403
    assert not fake_session.added


def test_dashboard_me_requires_session() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))

    response = client.get("/dashboard/session/me")

    assert response.status_code == 401


def test_dashboard_me_returns_current_admin_from_session() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))
    csrf_token = _csrf(client)
    assert _login(client, csrf_token).status_code == 200

    response = client.get("/dashboard/session/me")

    assert response.status_code == 200
    assert response.json()["login_id"] == "admin"
    assert response.json()["role"] == "ADMIN"
    assert "password" not in response.text
    assert "session" not in response.text


def test_dashboard_logout_revokes_session_and_clears_cookie() -> None:
    fake_session = _FakeSession(_user())
    client = TestClient(_build_app(fake_session))
    csrf_token = _csrf(client)
    assert _login(client, csrf_token).status_code == 200

    response = client.post("/dashboard/session/logout", headers={DASHBOARD_CSRF_HEADER: csrf_token})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert fake_session.added[0].revoked_at is not None
    assert f"{DASHBOARD_SESSION_COOKIE}=" in response.headers["set-cookie"]


def test_expired_dashboard_session_is_rejected() -> None:
    user = _user()
    fake_session = _FakeSession(user)
    raw_session = "expired-session"
    fake_session.add(
        DashboardSession(
            user_id=user.id,
            session_hash=hash_dashboard_session_token(raw_session),
            expires_at=utc_now() - timedelta(minutes=1),
        )
    )
    client = TestClient(_build_app(fake_session))
    client.cookies.set(DASHBOARD_SESSION_COOKIE, raw_session)

    response = client.get("/dashboard/session/me")

    assert response.status_code == 401
