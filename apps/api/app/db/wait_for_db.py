import asyncio
import sys

from sqlalchemy import text

from app.db.session import engine

MAX_ATTEMPTS = 30
SLEEP_SECONDS = 1


async def wait_for_db(max_attempts: int = MAX_ATTEMPTS, sleep_seconds: int = SLEEP_SECONDS) -> None:
    last_error_name = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            return
        except Exception as exc:
            last_error_name = exc.__class__.__name__
            print(f"[startup] database is not ready yet ({attempt}/{max_attempts}): {last_error_name}")
            if attempt < max_attempts:
                await asyncio.sleep(sleep_seconds)

    raise RuntimeError(f"database was not ready after {max_attempts} attempts: {last_error_name}")


def main() -> int:
    try:
        asyncio.run(wait_for_db())
    except Exception as exc:
        print(f"[startup] database readiness failed: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
