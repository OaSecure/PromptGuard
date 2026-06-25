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
        health.dependency("filter_config", "healthy", True, "FILTER_CONFIG_OK", "Filter config ready"),
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
                health.dependency("filter_config", "healthy", True, "FILTER_CONFIG_OK", "Filter config ready"),
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
                health.dependency("filter_config", "healthy", True, "FILTER_CONFIG_OK", "Filter config ready"),
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
                health.dependency("filter_config", "healthy", True, "FILTER_CONFIG_OK", "Filter config ready"),
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
                health.dependency("filter_config", "healthy", True, "FILTER_CONFIG_OK", "Filter config ready"),
            ],
        },
    )

    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


@pytest.mark.anyio
async def test_check_config_reports_missing_database_url(monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "get_settings",
        lambda: SimpleNamespace(database_url="", access_token_secret="access", refresh_token_secret="refresh"),
    )

    result = await health.check_config()

    assert result["name"] == "config"
    assert result["status"] == "unhealthy"
    assert result["code"] == "CONFIG_INVALID"


@pytest.mark.anyio
async def test_check_filter_config_reports_loadable_default_config() -> None:
    result = await health.check_filter_config()

    assert result["name"] == "filter_config"
    assert result["status"] == "healthy"
    assert result["required"] is True


@pytest.mark.anyio
async def test_check_torch_worker_reports_disabled_when_runtime_is_not_required(monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "get_settings",
        lambda: SimpleNamespace(
            worker_readiness_required=True,
            classifier_runtime_enabled=False,
            verifier_runtime_enabled=False,
        ),
    )

    result = await health.check_torch_worker()

    assert result["name"] == "torch_worker"
    assert result["status"] == "disabled"
    assert result["required"] is False


@pytest.mark.anyio
async def test_check_paddle_worker_reports_ready_with_warm_status(monkeypatch) -> None:
    class Snapshot:
        process_running = True
        warm = True
        in_flight_or_queued = 0
        last_failure_code = None

    class Client:
        def readiness_probe(self):
            return SimpleNamespace(ok=True)

        def status_snapshot(self):
            return Snapshot()

    monkeypatch.setattr(
        health,
        "get_settings",
            lambda: SimpleNamespace(
                worker_readiness_required=True,
                worker_readiness_timeout_ms=15000,
                ml_inference_queue_max_queue_size=32,
                paddle_worker_python_path="/opt/venvs/paddle/bin/python",
                paddle_worker_script_path="/app/scripts/paddle_ocr_worker.py",
                paddle_worker_payload_dir="/tmp/paddle",
        ),
    )
    monkeypatch.setattr(health, "cached_paddle_worker_client", lambda *_args: Client())

    result = await health.check_paddle_worker()

    assert result["name"] == "paddle_worker"
    assert result["status"] == "healthy"
    assert result["required"] is True
    assert result["code"] == "PADDLE_WORKER_READY"
    assert "warm=true" in result["message"]
    assert "queue_depth=0" in result["message"]


@pytest.mark.anyio
async def test_check_paddle_worker_failure_is_required_unhealthy(monkeypatch) -> None:
    class Client:
        def readiness_probe(self):
            return SimpleNamespace(ok=False, error_code="PADDLE_WORKER_INVALID_RESPONSE")

        def status_snapshot(self):
            return None

    monkeypatch.setattr(
        health,
        "get_settings",
            lambda: SimpleNamespace(
                worker_readiness_required=True,
                worker_readiness_timeout_ms=15000,
                ml_inference_queue_max_queue_size=32,
                paddle_worker_python_path="/opt/venvs/paddle/bin/python",
                paddle_worker_script_path="/app/scripts/paddle_ocr_worker.py",
                paddle_worker_payload_dir="/tmp/paddle",
        ),
    )
    monkeypatch.setattr(health, "cached_paddle_worker_client", lambda *_args: Client())

    result = await health.check_paddle_worker()

    assert result["name"] == "paddle_worker"
    assert result["status"] == "unhealthy"
    assert result["required"] is True
    assert result["code"] == "PADDLE_WORKER_INVALID_RESPONSE"
