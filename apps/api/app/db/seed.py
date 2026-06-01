import asyncio
import os

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth import User

DEFAULT_ADMIN_LOGIN_ID = "admin"
DEFAULT_ADMIN_PASSWORD = "1234"
INITIAL_ADMIN_PASSWORD_ENV = "PROMPTGUARD_INITIAL_ADMIN_PASSWORD"


def get_initial_admin_password() -> str:
    return os.getenv(INITIAL_ADMIN_PASSWORD_ENV, DEFAULT_ADMIN_PASSWORD)


async def ensure_default_admin(session: AsyncSession) -> User:
    result = await session.execute(
        select(User)
        .where(or_(User.login_id_normalized == DEFAULT_ADMIN_LOGIN_ID, User.role == "ADMIN"))
        .order_by(User.created_at.asc())
        .limit(1)
    )
    admin = result.scalar_one_or_none()
    if admin is not None:
        admin.login_id = DEFAULT_ADMIN_LOGIN_ID
        admin.login_id_normalized = DEFAULT_ADMIN_LOGIN_ID
        admin.username = DEFAULT_ADMIN_LOGIN_ID
        admin.role = "ADMIN"
        admin.status = "ACTIVE"
        return admin

    admin = User(
        login_id=DEFAULT_ADMIN_LOGIN_ID,
        login_id_normalized=DEFAULT_ADMIN_LOGIN_ID,
        username=DEFAULT_ADMIN_LOGIN_ID,
        email=None,
        email_normalized=None,
        department=None,
        display_name="PromptGuard Admin",
        role="ADMIN",
        status="ACTIVE",
        password_hash=hash_password(get_initial_admin_password()),
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )
    session.add(admin)
    return admin


async def seed_initial_data() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await ensure_default_admin(session)


def main() -> int:
    asyncio.run(seed_initial_data())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
