import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.routes import dashboard_status
from app.routes.auth import get_db_session, require_admin


class _FakeSession:
    def __init__(self, *, fail_filter_rules: bool = False):
        self.fail_filter_rules = fail_filter_rules

    async def execute(self, _statement):
        if self.fail_filter_rules:
            raise RuntimeError("postgres://user:password@localhost/db raw exception secret token")
        return SimpleNamespace()

    async def get(self, _model, _item_id):
        return None


def _user(role: str = "ADMIN", status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role=role, status=status)


def _bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _client(monkeypatch, *, user=None, fail_filter_rules: bool = False, health_status: str = "healthy") -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_status.router)

    async def override_session():
        yield _FakeSession(fail_filter_rules=fail_filter_rules)

    async def fake_build_health(include_optional: bool = False):
        assert include_optional is False
        return {
            "status": health_status,
            "service": "promptguard-api",
            "version": "0.1.0",
            "environment": "development",
            "checked_at": "2026-05-31T00:00:00Z",
            "dependencies": [
                {
                    "name": "postgres",
                    "status": "healthy",
                    "required": True,
                    "code": "POSTGRES_OK",
                    "message": "postgres://user:password@localhost/db",
                },
                {
                    "name": "migrations",
                    "status": "healthy" if health_status != "unhealthy" else "unhealthy",
                    "required": True,
                    "code": "MIGRATIONS_CURRENT",
                    "message": "traceback secret token",
                },
                {
                    "name": "config",
                    "status": "healthy",
                    "required": True,
                    "code": "CONFIG_OK",
                    "message": "env detail",
                },
            ],
        }

    app.dependency_overrides[get_db_session] = override_session
    monkeypatch.setattr(dashboard_status, "build_health", fake_build_health)
    if user is not None:
        async def override_admin():
            if user.status != "ACTIVE":
                from fastapi import HTTPException, status

                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")
            if user.role != "ADMIN":
                from fastapi import HTTPException, status

                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
            return user

        app.dependency_overrides[require_admin] = override_admin
        app.dependency_overrides[dashboard_status.require_admin] = override_admin
    return TestClient(app)


def test_dashboard_status_without_credentials_returns_401(monkeypatch) -> None:
    response = _client(monkeypatch).get("/dashboard/status")

    assert response.status_code == 401


def test_dashboard_status_with_user_role_returns_403(monkeypatch) -> None:
    user = _user(role="USER")
    response = _client(monkeypatch, user=user).get("/dashboard/status", headers=_bearer_header(user.id))

    assert response.status_code == 403


def test_dashboard_status_with_admin_returns_sanitized_allowlist(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user).get("/dashboard/status", headers=_bearer_header(user.id))

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"status", "last_checked", "api", "postgres", "migrations", "filter_rules"}
    assert body["last_checked"] == "2026-05-31T00:00:00Z"
    assert body["api"] == {"status": "healthy"}
    assert body["postgres"] == {"status": "healthy"}
    assert body["migrations"] == {"status": "healthy"}
    assert body["filter_rules"] == {"status": "healthy"}
    assert all(set(body[key]) == {"status"} for key in ["api", "postgres", "migrations", "filter_rules"])


def test_dashboard_status_does_not_leak_raw_details(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user, fail_filter_rules=True).get(
        "/dashboard/status",
        headers=_bearer_header(user.id),
    )
    encoded = json.dumps(response.json(), ensure_ascii=False).casefold()

    assert response.status_code == 200
    assert response.json()["filter_rules"] == {"status": "unknown"}
    forbidden = [
        "postgres://",
        "password",
        "secret",
        "token",
        "traceback",
        "runtimeerror",
        "environment",
        "keyword",
        "pattern",
        "config_json",
        "editable_fields",
        "env detail",
    ]
    for value in forbidden:
        assert value not in encoded


def test_dashboard_status_returns_503_when_required_dependency_unhealthy(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user, health_status="unhealthy").get(
        "/dashboard/status",
        headers=_bearer_header(user.id),
    )

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
