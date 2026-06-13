import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.routes import dashboard_status
from app.routes.auth import get_db_session


class _FakeSession:
    def __init__(self, *, fail_filter_rules: bool = False):
        self.fail_filter_rules = fail_filter_rules

    async def execute(self, _statement):
        if self.fail_filter_rules:
            raise RuntimeError("postgres://user:password@localhost/db raw exception secret token")
        return SimpleNamespace()


def _user(role: str = "ADMIN", status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role=role, status=status)


def _bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _client(
    monkeypatch,
    *,
    user=None,
    fail_filter_rules: bool = False,
    health_status: str = "healthy",
    checked_at: str | None = "2026-06-01T00:00:00Z",
) -> TestClient:
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
            "checked_at": checked_at,
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

        app.dependency_overrides[dashboard_status.require_dashboard_admin_session] = override_admin
    return TestClient(app)


def test_dashboard_status_without_credentials_returns_401(monkeypatch) -> None:
    response = _client(monkeypatch).get("/dashboard/status")

    assert response.status_code == 401


def test_dashboard_status_rejects_bearer_only_access(monkeypatch) -> None:
    response = _client(monkeypatch).get("/dashboard/status", headers=_bearer_header(uuid4()))

    assert response.status_code == 401


def test_dashboard_status_with_user_role_returns_403(monkeypatch) -> None:
    user = _user(role="USER")
    response = _client(monkeypatch, user=user).get("/dashboard/status")

    assert response.status_code == 403


def test_dashboard_status_with_admin_returns_flat_allowlist(monkeypatch) -> None:
    user = _user()
    monkeypatch.setattr(dashboard_status, "collect_server_ipv4_addresses", lambda: ["192.168.0.10"])
    response = _client(monkeypatch, user=user).get("/dashboard/status", headers={"host": "localhost:8000"})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {
        "status",
        "last_checked",
        "api_status",
        "postgres_status",
        "migration_status",
        "filter_rules_status",
        "extension_connection",
    }
    assert body["last_checked"] == "2026-06-01T00:00:00Z"
    assert body["api_status"] == "healthy"
    assert body["postgres_status"] == "healthy"
    assert body["migration_status"] == "healthy"
    assert body["filter_rules_status"] == "healthy"
    assert "api" not in body
    assert "postgres" not in body
    assert "migrations" not in body
    assert "filter_rules" not in body
    assert "dependencies" not in body
    assert body["extension_connection"] == {
        "internal_api_origins": ["http://192.168.0.10:8000"],
        "excluded_internal_api_origins": [],
        "admin_local_api_origin": "http://localhost:8000",
        "external_api_origin": None,
        "api_port": "8000",
    }


def test_dashboard_status_reports_forwarded_external_origin(monkeypatch) -> None:
    user = _user()
    monkeypatch.setattr(dashboard_status, "collect_server_ipv4_addresses", lambda: ["10.1.2.3"])
    response = _client(monkeypatch, user=user).get(
        "/dashboard/status",
        headers={
            "host": "localhost:8000",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "promptguard.example.com",
        },
    )

    assert response.status_code == 200
    assert response.json()["extension_connection"] == {
        "internal_api_origins": ["http://10.1.2.3:8000"],
        "excluded_internal_api_origins": [],
        "admin_local_api_origin": "http://localhost:8000",
        "external_api_origin": "https://promptguard.example.com",
        "api_port": "8000",
    }


def test_dashboard_status_excludes_docker_bridge_origin_from_recommended_extension_urls(monkeypatch) -> None:
    user = _user()
    monkeypatch.setattr(dashboard_status, "collect_server_ipv4_addresses", lambda: ["172.19.0.3", "192.168.0.10"])
    monkeypatch.setattr(dashboard_status, "is_running_in_container", lambda: True)
    response = _client(monkeypatch, user=user).get("/dashboard/status", headers={"host": "localhost:8000"})

    body = response.json()["extension_connection"]
    assert response.status_code == 200
    assert body["internal_api_origins"] == ["http://192.168.0.10:8000"]
    assert body["excluded_internal_api_origins"] == ["http://172.19.0.3:8000"]


def test_dashboard_status_does_not_leak_raw_details(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user, fail_filter_rules=True).get("/dashboard/status")
    encoded = json.dumps(response.json(), ensure_ascii=False).casefold()

    assert response.status_code == 503
    assert response.json()["filter_rules_status"] == "unhealthy"
    forbidden = [
        "postgres://",
        "password",
        "secret",
        "token",
        "stack",
        "traceback",
        "runtimeerror",
        "environment",
        "keyword",
        "pattern",
        "config_json",
        "editable_fields",
        "env detail",
        "message",
        "code",
        "request_id",
        "service",
        "version",
        "redis",
    ]
    for value in forbidden:
        assert value not in encoded


def test_dashboard_status_returns_503_when_required_dependency_unhealthy(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user, health_status="unhealthy").get("/dashboard/status")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


def test_dashboard_status_generates_last_checked_when_health_timestamp_is_invalid(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user, checked_at="not-a-date").get("/dashboard/status")
    body = response.json()

    assert response.status_code == 200
    assert body["last_checked"] != ""
    assert body["last_checked"] != "not-a-date"


def test_dashboard_status_values_are_limited_to_document_contract(monkeypatch) -> None:
    user = _user()
    response = _client(monkeypatch, user=user).get("/dashboard/status")
    body = response.json()
    allowed = {"healthy", "degraded", "unhealthy", "unknown"}

    assert body["status"] in allowed
    assert body["api_status"] in allowed
    assert body["postgres_status"] in allowed
    assert body["migration_status"] in allowed
    assert body["filter_rules_status"] in allowed
