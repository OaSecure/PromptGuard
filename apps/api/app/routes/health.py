from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])


async def check_database() -> dict[str, Any]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": exc.__class__.__name__}


async def check_redis() -> dict[str, Any]:
    client = Redis.from_url(get_settings().redis_url)
    try:
        pong = await client.ping()
        return {"status": "ok" if pong else "error"}
    except Exception as exc:
        return {"status": "error", "detail": exc.__class__.__name__}
    finally:
        await client.aclose()


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    dependencies = {
        "database": await check_database(),
        "redis": await check_redis(),
    }
    healthy = all(item["status"] == "ok" for item in dependencies.values())

    return {
        "status": "ok" if healthy else "degraded",
        "service": "promptguard-api",
        "dependencies": dependencies,
    }
