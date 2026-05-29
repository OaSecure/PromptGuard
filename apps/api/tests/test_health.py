from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import health


def build_test_client(monkeypatch, health_payload: dict) -> TestClient:
    async def fake_build_health(include_optional: bool = True) -> dict:
        return health_payload

    monkeypatch.setattr(health, "build_health", fake_build_health)
    app = FastAPI()
    app.include_router(health.router)
    return TestClient(app)


def test_aggregate_status_is_unhealthy_when_required_dependency_fails() -> None:
    dependencies = [
        health.dependency("postgres", "unhealthy", True, "POSTGRES_UNAVAILABLE", "Database unavailable"),
        health.dependency("redis", "disabled", False, "REDIS_DISABLED", "Redis disabled"),
    ]

    assert health.aggregate_status(dependencies) == "unhealthy"


def test_aggregate_status_is_healthy_when_only_optional_redis_is_disabled() -> None:
    dependencies = [
        health.dependency("postgres", "healthy", True, "POSTGRES_OK", "Database ready"),
        health.dependency("migrations", "healthy", True, "MIGRATIONS_CURRENT", "Migrations current"),
        health.dependency("config", "healthy", True, "CONFIG_OK", "Config ready"),
        health.dependency("redis", "disabled", False, "REDIS_DISABLED", "Redis disabled"),
    ]

    assert health.aggregate_status(dependencies) == "healthy"


@pytest.mark.anyio
async def test_check_redis_reports_disabled_when_url_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(redis_url=""))

    result = await health.check_redis()

    assert result["name"] == "redis"
    assert result["status"] == "disabled"
    assert result["required"] is False


def test_readyz_returns_200_when_required_dependencies_are_healthy(monkeypatch) -> None:
    client = build_test_client(
        monkeypatch,
        {
            "status": "healthy",
            "dependencies": [
                health.dependency("postgres", "healthy", True, "POSTGRES_OK", "Database ready"),
                health.dependency("migrations", "healthy", True, "MIGRATIONS_CURRENT", "Migrations current"),
                health.dependency("config", "healthy", True, "CONFIG_OK", "Config ready"),
            ],
        },
    )

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readyz_returns_503_when_migrations_are_unhealthy(monkeypatch) -> None:
    client = build_test_client(
        monkeypatch,
        {
            "status": "unhealthy",
            "dependencies": [
                health.dependency("postgres", "healthy", True, "POSTGRES_OK", "Database ready"),
                health.dependency("migrations", "unhealthy", True, "MIGRATIONS_OUTDATED", "Migrations outdated"),
                health.dependency("config", "healthy", True, "CONFIG_OK", "Config ready"),
            ],
        },
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


def test_healthz_returns_200_when_only_optional_redis_is_degraded(monkeypatch) -> None:
    client = build_test_client(
        monkeypatch,
        {
            "status": "degraded",
            "dependencies": [
                health.dependency("postgres", "healthy", True, "POSTGRES_OK", "Database ready"),
                health.dependency("migrations", "healthy", True, "MIGRATIONS_CURRENT", "Migrations current"),
                health.dependency("config", "healthy", True, "CONFIG_OK", "Config ready"),
                health.dependency("redis", "degraded", False, "REDIS_UNAVAILABLE", "Redis unavailable"),
            ],
        },
    )

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_healthz_returns_503_when_required_dependency_is_unhealthy(monkeypatch) -> None:
    client = build_test_client(
        monkeypatch,
        {
            "status": "unhealthy",
            "dependencies": [
                health.dependency("postgres", "unhealthy", True, "POSTGRES_UNAVAILABLE", "Database unavailable"),
                health.dependency("migrations", "healthy", True, "MIGRATIONS_CURRENT", "Migrations current"),
                health.dependency("config", "healthy", True, "CONFIG_OK", "Config ready"),
            ],
        },
    )

    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
