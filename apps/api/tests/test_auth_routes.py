import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.password import hash_password
from app.routes import auth as auth_routes


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


def _build_app(fake_session: _FakeSession) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)

    async def override_session():
        yield fake_session

    app.dependency_overrides[auth_routes.get_db_session] = override_session
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
