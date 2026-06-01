import uuid
from datetime import timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.password import hash_password
from app.core.tokens import hash_dashboard_csrf_token, hash_dashboard_session_token, utc_now
from app.routes import dashboard_session


class _ScalarResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        return self.item


class _RowResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _FakeSession:
    def __init__(self, *, user=None, dashboard_session_row=None):
        self.user = user
        self.dashboard_session_row = dashboard_session_row
        self.added = []
        self.commits = 0
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "dashboard_sessions" in statement_text:
            return _RowResult(self.dashboard_session_row)
        return _ScalarResult(self.user)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


def _user(*, role: str = "ADMIN", status: str = "ACTIVE"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id=role.lower(),
        login_id_normalized=role.lower(),
        username=role.lower(),
        email=None,
        department="Security",
        display_name="PromptGuard Admin",
        role=role,
        status=status,
        password_hash=hash_password("1234"),
        last_login_at=None,
    )


def _session_row(*, raw_session: str = "raw-dashboard-session", csrf_token: str = "csrf-token", user=None, **values):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=(user or _user()).id,
        session_hash=hash_dashboard_session_token(raw_session),
        csrf_hash=hash_dashboard_csrf_token(csrf_token),
        expires_at=values.get("expires_at", utc_now() + timedelta(hours=1)),
        revoked_at=values.get("revoked_at"),
        last_seen_at=None,
    )


def _client(fake_session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_session.router)

    async def override_session():
        yield fake_session

    app.dependency_overrides[dashboard_session.get_db_session] = override_session
    return TestClient(app)


def _csrf(client: TestClient) -> str:
    response = client.get("/dashboard/session/csrf")
    assert response.status_code == 200
    csrf_token = response.json()["csrf_token"]
    assert client.cookies.get("promptguard_dashboard_csrf") == csrf_token
    return csrf_token


def test_dashboard_csrf_sets_readable_csrf_cookie_without_session() -> None:
    client = _client(_FakeSession())

    response = client.get("/dashboard/session/csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "promptguard_dashboard_csrf=" in response.headers["set-cookie"]
    assert "httponly" not in response.headers["set-cookie"].lower()
    assert "promptguard_dashboard_session" not in response.headers["set-cookie"]


def test_admin_login_creates_hash_only_httponly_session() -> None:
    fake_session = _FakeSession(user=_user())
    client = _client(fake_session)
    csrf_token = _csrf(client)

    response = client.post(
        "/dashboard/session/login",
        headers={"X-CSRF-Token": csrf_token},
        json={"login_id": "admin", "password": "1234"},
    )

    body = response.json()
    created_session = fake_session.added[0]
    raw_session_cookie = client.cookies.get("promptguard_dashboard_session")
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["user"]["role"] == "ADMIN"
    assert body["csrf_token"] == csrf_token
    assert raw_session_cookie
    assert raw_session_cookie not in created_session.session_hash
    assert created_session.login_id == "admin"
    assert created_session.session_hash == hash_dashboard_session_token(raw_session_cookie)
    assert created_session.csrf_hash == hash_dashboard_csrf_token(csrf_token)
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert raw_session_cookie not in response.text
    assert fake_session.user.last_login_at is not None
    assert fake_session.commits == 1


def test_dashboard_login_rejects_user_credentials_with_403() -> None:
    fake_session = _FakeSession(user=_user(role="USER"))
    client = _client(fake_session)
    csrf_token = _csrf(client)

    response = client.post(
        "/dashboard/session/login",
        headers={"X-CSRF-Token": csrf_token},
        json={"login_id": "user", "password": "1234"},
    )

    assert response.status_code == 403
    assert not fake_session.added
    assert client.cookies.get("promptguard_dashboard_session") is None


def test_dashboard_login_rejects_disabled_admin_with_403() -> None:
    fake_session = _FakeSession(user=_user(status="DISABLED"))
    client = _client(fake_session)
    csrf_token = _csrf(client)

    response = client.post(
        "/dashboard/session/login",
        headers={"X-CSRF-Token": csrf_token},
        json={"login_id": "admin", "password": "1234"},
    )

    assert response.status_code == 403
    assert not fake_session.added


def test_dashboard_login_rejects_invalid_credentials_with_401() -> None:
    fake_session = _FakeSession(user=_user())
    client = _client(fake_session)
    csrf_token = _csrf(client)

    response = client.post(
        "/dashboard/session/login",
        headers={"X-CSRF-Token": csrf_token},
        json={"login_id": "admin", "password": "wrong"},
    )

    assert response.status_code == 401
    assert not fake_session.added


def test_dashboard_login_requires_matching_csrf_header_and_cookie() -> None:
    fake_session = _FakeSession(user=_user())
    client = _client(fake_session)
    csrf_token = _csrf(client)

    missing_response = client.post(
        "/dashboard/session/login",
        json={"login_id": "admin", "password": "1234"},
    )
    mismatch_response = client.post(
        "/dashboard/session/login",
        headers={"X-CSRF-Token": f"{csrf_token}-bad"},
        json={"login_id": "admin", "password": "1234"},
    )

    assert missing_response.status_code == 403
    assert mismatch_response.status_code == 403
    assert not fake_session.added


def test_dashboard_me_returns_safe_metadata_for_active_admin_session() -> None:
    user = _user()
    raw_session = "session-for-me"
    row = _session_row(raw_session=raw_session, user=user)
    fake_session = _FakeSession(dashboard_session_row=(row, user))
    client = _client(fake_session)
    client.cookies.set("promptguard_dashboard_session", raw_session)

    response = client.get("/dashboard/session/me")

    body = response.json()
    assert response.status_code == 200
    assert body["login_id"] == "admin"
    assert body["role"] == "ADMIN"
    assert "password" not in response.text
    assert "session" not in response.text
    assert row.last_seen_at is not None
    assert fake_session.commits == 1


def test_dashboard_me_rejects_missing_expired_revoked_or_non_admin_session() -> None:
    client = _client(_FakeSession())
    assert client.get("/dashboard/session/me").status_code == 401

    user = _user()
    expired = _session_row(raw_session="expired", user=user, expires_at=utc_now() - timedelta(seconds=1))
    expired_client = _client(_FakeSession(dashboard_session_row=(expired, user)))
    expired_client.cookies.set("promptguard_dashboard_session", "expired")
    assert expired_client.get("/dashboard/session/me").status_code == 401

    revoked = _session_row(raw_session="revoked", user=user, revoked_at=utc_now())
    revoked_client = _client(_FakeSession(dashboard_session_row=(revoked, user)))
    revoked_client.cookies.set("promptguard_dashboard_session", "revoked")
    assert revoked_client.get("/dashboard/session/me").status_code == 401

    non_admin = _user(role="USER")
    non_admin_row = _session_row(raw_session="non-admin", user=non_admin)
    non_admin_client = _client(_FakeSession(dashboard_session_row=(non_admin_row, non_admin)))
    non_admin_client.cookies.set("promptguard_dashboard_session", "non-admin")
    assert non_admin_client.get("/dashboard/session/me").status_code == 403


def test_dashboard_logout_requires_csrf_revokes_session_and_clears_cookies() -> None:
    user = _user()
    raw_session = "session-for-logout"
    csrf_token = "csrf-for-logout"
    row = _session_row(raw_session=raw_session, csrf_token=csrf_token, user=user)
    fake_session = _FakeSession(dashboard_session_row=(row, user))
    client = _client(fake_session)
    client.cookies.set("promptguard_dashboard_session", raw_session)
    client.cookies.set("promptguard_dashboard_csrf", csrf_token)

    missing_response = client.post("/dashboard/session/logout")
    response = client.post("/dashboard/session/logout", headers={"X-CSRF-Token": csrf_token})

    assert missing_response.status_code == 403
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert row.revoked_at is not None
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "promptguard_dashboard_session=\"\"" in set_cookie
    assert "promptguard_dashboard_csrf=\"\"" in set_cookie


def test_dashboard_session_routes_are_registered_on_main_app() -> None:
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/dashboard/session/csrf" in paths
    assert "/dashboard/session/login" in paths
    assert "/dashboard/session/logout" in paths
    assert "/dashboard/session/me" in paths
