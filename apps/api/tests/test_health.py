from types import SimpleNamespace

import pytest

from app.routes import health


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
