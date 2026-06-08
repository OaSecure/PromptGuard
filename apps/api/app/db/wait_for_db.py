import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def wait_for_database(
    database_url: str,
    *,
    max_attempts: int = 30,
    sleep_seconds: float = 1.0,
) -> None:
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        engine = create_async_engine(database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            return
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            await asyncio.sleep(sleep_seconds)
        finally:
            await engine.dispose()

    assert last_error is not None
    raise last_error


def wait_for_configured_database() -> None:
    asyncio.run(wait_for_database(get_settings().database_url))
