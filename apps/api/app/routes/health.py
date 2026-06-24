from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.runtime.worker_clients import cached_paddle_worker_client, cached_torch_worker_client

router = APIRouter(tags=["health"])

SERVICE_NAME = "promptguard-api"
SERVICE_VERSION = "0.1.0"


def checked_at() -> str:
    return datetime.now(UTC).isoformat()


def dependency(name: str, status_value: str, required: bool, code: str, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status_value,
        "required": required,
        "code": code,
        "message": message,
    }


def repo_api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_migration_head() -> str:
    alembic_config = Config(str(repo_api_root() / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(repo_api_root() / "alembic"))
    script = ScriptDirectory.from_config(alembic_config)
    return script.get_current_head()


async def check_database() -> dict[str, Any]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
        return dependency("postgres", "healthy", True, "POSTGRES_OK", "PostgreSQL connection is ready")
    except Exception as exc:
        return dependency(
            "postgres",
            "unhealthy",
            True,
            "POSTGRES_UNAVAILABLE",
            f"PostgreSQL check failed: {exc.__class__.__name__}",
        )


async def check_migrations() -> dict[str, Any]:
    try:
        expected_head = get_migration_head()
        async with engine.connect() as connection:
            result = await connection.execute(text("select version_num from alembic_version"))
            current_version = result.scalar_one_or_none()

        if current_version == expected_head:
            return dependency("migrations", "healthy", True, "MIGRATIONS_CURRENT", "Database migrations are current")

        return dependency(
            "migrations",
            "unhealthy",
            True,
            "MIGRATIONS_OUTDATED",
            "Database migrations are not current",
        )
    except Exception as exc:
        return dependency(
            "migrations",
            "unhealthy",
            True,
            "MIGRATIONS_UNKNOWN",
            f"Migration check failed: {exc.__class__.__name__}",
        )


async def check_config() -> dict[str, Any]:
    settings = get_settings()
    missing = []
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if not settings.access_token_secret:
        missing.append("ACCESS_TOKEN_SECRET")
    if not settings.refresh_token_secret:
        missing.append("REFRESH_TOKEN_SECRET")

    if missing:
        return dependency(
            "config",
            "unhealthy",
            True,
            "CONFIG_INVALID",
            "Required configuration is missing",
        )

    return dependency("config", "healthy", True, "CONFIG_OK", "Required configuration is present")


async def check_filter_config() -> dict[str, Any]:
    return dependency(
        "filter_config",
        "healthy",
        True,
        "FILTER_CONFIG_OK",
        "Default filter configuration is loadable",
    )


async def check_torch_worker() -> dict[str, Any]:
    settings = get_settings()
    required = settings.worker_readiness_required and (
        settings.classifier_runtime_enabled or settings.verifier_runtime_enabled
    )
    if not required:
        return dependency("torch_worker", "disabled", False, "TORCH_WORKER_DISABLED", "Torch worker readiness is not required")
    if settings.classifier_manifest_path_value() is None or settings.verifier_manifest_path_value() is None:
        return dependency("torch_worker", "unhealthy", True, "TORCH_WORKER_CONFIG_MISSING", "Torch worker manifests are not configured")

    client = cached_torch_worker_client(
        settings.torch_worker_python_path,
        settings.torch_worker_script_path,
        settings.torch_worker_payload_dir,
        settings.worker_readiness_timeout_ms,
        settings.ml_inference_queue_max_queue_size,
    )
    result = client.readiness_probe()
    snapshot = client.status_snapshot()
    message = _worker_message("Torch worker is ready", snapshot)
    if result.ok:
        return dependency("torch_worker", "healthy", True, "TORCH_WORKER_READY", message)
    return dependency(
        "torch_worker",
        "unhealthy",
        True,
        result.error_code or "TORCH_WORKER_UNAVAILABLE",
        _worker_message("Torch worker readiness failed", snapshot),
    )


async def check_paddle_worker() -> dict[str, Any]:
    settings = get_settings()
    required = settings.worker_readiness_required
    if not required:
        return dependency("paddle_worker", "disabled", False, "PADDLE_WORKER_DISABLED", "PaddleOCR worker readiness is not required")

    client = cached_paddle_worker_client(
        settings.paddle_worker_python_path,
        settings.paddle_worker_script_path,
        settings.paddle_worker_payload_dir,
        settings.worker_readiness_timeout_ms,
        settings.ml_inference_queue_max_queue_size,
    )
    result = client.readiness_probe()
    snapshot = client.status_snapshot()
    if result.ok:
        return dependency("paddle_worker", "healthy", True, "PADDLE_WORKER_READY", _worker_message("PaddleOCR worker is ready", snapshot))
    return dependency(
        "paddle_worker",
        "unhealthy",
        True,
        result.error_code or "PADDLE_WORKER_UNAVAILABLE",
        _worker_message("PaddleOCR worker readiness failed", snapshot),
    )


async def check_redis() -> dict[str, Any]:
    redis_url = get_settings().redis_url.strip()
    if not redis_url:
        return dependency("redis", "disabled", False, "REDIS_DISABLED", "Redis is not enabled for this deployment")

    client = Redis.from_url(redis_url)
    try:
        pong = await client.ping()
        if pong:
            return dependency("redis", "healthy", False, "REDIS_OK", "Redis connection is ready")
        return dependency("redis", "degraded", False, "REDIS_PING_FAILED", "Redis ping did not return pong")
    except Exception as exc:
        return dependency("redis", "degraded", False, "REDIS_UNAVAILABLE", f"Redis check failed: {exc.__class__.__name__}")
    finally:
        await client.aclose()


def aggregate_status(dependencies: list[dict[str, Any]]) -> str:
    required_dependencies = [item for item in dependencies if item["required"]]
    if any(item["status"] == "unhealthy" for item in required_dependencies):
        return "unhealthy"
    if any(item["status"] in {"unhealthy", "degraded"} for item in dependencies):
        return "degraded"
    return "healthy"


async def build_health(include_optional: bool = True) -> dict[str, Any]:
    dependencies = [
        await check_database(),
        await check_migrations(),
        await check_config(),
        await check_filter_config(),
        await check_torch_worker(),
        await check_paddle_worker(),
    ]
    if include_optional:
        dependencies.append(await check_redis())

    return {
        "status": aggregate_status(dependencies),
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "environment": get_settings().environment,
        "checked_at": checked_at(),
        "dependencies": dependencies,
    }


def _worker_message(prefix: str, snapshot: object) -> str:
    if snapshot is None:
        return f"{prefix}; process_running=false warm=false queue_depth=0 failure_code=none"
    process_running = getattr(snapshot, "process_running", False)
    warm = getattr(snapshot, "warm", False)
    queue_depth = getattr(snapshot, "in_flight_or_queued", 0)
    requests_total = getattr(snapshot, "requests_total", 0)
    succeeded_total = getattr(snapshot, "succeeded_total", 0)
    failed_total = getattr(snapshot, "failed_total", 0)
    failure_code = getattr(snapshot, "last_failure_code", None) or "none"
    return (
        f"{prefix}; process_running={str(process_running).lower()} warm={str(warm).lower()} "
        f"queue_depth={queue_depth} requests_total={requests_total} succeeded_total={succeeded_total} "
        f"failed_total={failed_total} failure_code={failure_code}"
    )


@router.get("/livez")
async def livez() -> dict[str, Any]:
    return {
        "status": "alive",
        "service": SERVICE_NAME,
        "checked_at": checked_at(),
    }


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, Any]:
    health = await build_health(include_optional=False)
    if health["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health


@router.get("/healthz")
async def healthz(response: Response) -> dict[str, Any]:
    health = await build_health(include_optional=True)
    if health["status"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health
