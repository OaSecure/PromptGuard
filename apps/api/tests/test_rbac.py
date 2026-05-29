from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.routes import status as status_route
from app.routes.auth import get_db_session, require_admin


class _FakeSession:
    def __init__(self, user):
        self.user = user

    async def get(self, model, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None


def build_status_client(monkeypatch, user=None, health_status: str = "healthy", redis_status: str = "disabled") -> TestClient:
    app = FastAPI()
    app.include_router(status_route.router)

    async def override_session():
        yield _FakeSession(user)

    async def fake_build_health(include_optional: bool = True):
        dependencies = [
            {"name": "postgres", "status": "healthy", "required": True, "code": "POSTGRES_OK", "message": "ok"},
            {
                "name": "migrations",
                "status": "healthy" if health_status != "unhealthy" else "unhealthy",
                "required": True,
                "code": "MIGRATIONS_CURRENT",
                "message": "ok",
            },
        ]
        if include_optional:
            dependencies.append(
                {
                    "name": "redis",
                    "status": redis_status,
                    "required": False,
                    "code": "REDIS_TEST",
                    "message": "optional",
                }
            )
        return {
            "status": health_status,
            "service": "promptguard-api",
            "version": "0.1.0",
            "environment": "development",
            "checked_at": "2026-05-29T00:00:00Z",
            "dependencies": dependencies,
        }

    app.dependency_overrides[get_db_session] = override_session
    monkeypatch.setattr(status_route, "build_health", fake_build_health)
    return TestClient(app)


def bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def fake_user(role: str = "ADMIN", status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role=role, status=status)


@pytest.mark.anyio
async def test_require_admin_accepts_admin_user() -> None:
    user = SimpleNamespace(role="ADMIN")

    assert await require_admin(user) is user


@pytest.mark.anyio
async def test_require_admin_rejects_user_role() -> None:
    user = SimpleNamespace(role="USER")

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "admin access required"


def test_server_status_route_uses_admin_guard() -> None:
    route = next(route for route in status_route.router.routes if getattr(route, "path", None) == "/status/server")
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}

    assert require_admin in dependency_calls


def test_server_status_without_credentials_returns_401(monkeypatch) -> None:
    client = build_status_client(monkeypatch, user=fake_user())

    response = client.get("/status/server")

    assert response.status_code == 401


def test_server_status_with_user_role_returns_403(monkeypatch) -> None:
    user = fake_user(role="USER")
    client = build_status_client(monkeypatch, user=user)

    response = client.get("/status/server", headers=bearer_header(user.id))

    assert response.status_code == 403


def test_server_status_with_admin_role_returns_200(monkeypatch) -> None:
    user = fake_user(role="ADMIN")
    client = build_status_client(monkeypatch, user=user)

    response = client.get("/status/server", headers=bearer_header(user.id))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "healthy"
    assert "environment" not in body
    assert "dependencies" not in body
    assert body["postgres"]["status"] == "healthy"
    assert body["migrations"]["status"] == "healthy"


def test_server_status_with_disabled_admin_returns_403(monkeypatch) -> None:
    user = fake_user(role="ADMIN", status="DISABLED")
    client = build_status_client(monkeypatch, user=user)

    response = client.get("/status/server", headers=bearer_header(user.id))

    assert response.status_code == 403


def test_server_status_returns_503_when_required_dependency_unhealthy(monkeypatch) -> None:
    user = fake_user(role="ADMIN")
    client = build_status_client(monkeypatch, user=user, health_status="unhealthy")

    response = client.get("/status/server", headers=bearer_header(user.id))

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


def test_server_status_keeps_200_for_optional_redis_degraded(monkeypatch) -> None:
    user = fake_user(role="ADMIN")
    client = build_status_client(monkeypatch, user=user, health_status="degraded", redis_status="degraded")

    response = client.get("/status/server", headers=bearer_header(user.id))

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
