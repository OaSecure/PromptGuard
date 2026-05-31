from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth import User


DEFAULT_ADMIN_LOGIN_ID = "admin"
DEFAULT_ADMIN_LOGIN_ID_NORMALIZED = "admin"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_DISPLAY_NAME = "PromptGuard Admin"


async def ensure_default_admin(session: AsyncSession) -> bool:
    result = await session.execute(
        select(User).where(User.login_id_normalized == DEFAULT_ADMIN_LOGIN_ID_NORMALIZED)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return False

    settings = get_settings()
    admin = User(
        login_id=DEFAULT_ADMIN_LOGIN_ID,
        login_id_normalized=DEFAULT_ADMIN_LOGIN_ID_NORMALIZED,
        username=DEFAULT_ADMIN_USERNAME,
        email=None,
        email_normalized=None,
        department=None,
        display_name=DEFAULT_ADMIN_DISPLAY_NAME,
        role="ADMIN",
        status="ACTIVE",
        password_hash=hash_password(settings.initial_admin_password),
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )
    session.add(admin)
    await session.flush()
    return True


async def seed_initial_data() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await ensure_default_admin(session)


def main() -> None:
    asyncio.run(seed_initial_data())


if __name__ == "__main__":
    main()
