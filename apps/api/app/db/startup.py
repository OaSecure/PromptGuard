import asyncio
import os
import subprocess
import sys

from app.db.seed import seed_default_admin
from app.db.wait_for_db import wait_for_configured_database

DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = "8000"


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


def run_alembic_upgrade() -> None:
    run_checked([sys.executable, "-m", "alembic", "upgrade", "head"])


def run_default_admin_seed() -> None:
    asyncio.run(seed_default_admin())


def build_uvicorn_command() -> list[str]:
    host = os.getenv("PROMPTGUARD_API_HOST", DEFAULT_API_HOST)
    port = os.getenv("PROMPTGUARD_API_PORT", DEFAULT_API_PORT)
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        port,
        "--reload",
    ]


def run_uvicorn() -> None:
    run_checked(build_uvicorn_command())


def main() -> None:
    wait_for_configured_database()
    run_alembic_upgrade()
    run_default_admin_seed()
    run_uvicorn()


if __name__ == "__main__":
    main()
