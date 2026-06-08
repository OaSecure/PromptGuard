import os
import uuid

from sqlalchemy import or_, select

from app.core.password import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth import User

DEFAULT_ADMIN_LOGIN_ID = "admin"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_DISPLAY_NAME = "PromptGuard Admin"
DEFAULT_ADMIN_ROLE = "ADMIN"
DEFAULT_ADMIN_STATUS = "ACTIVE"
INITIAL_ADMIN_PASSWORD_ENV = "PROMPTGUARD_INITIAL_ADMIN_PASSWORD"
DEFAULT_INITIAL_ADMIN_PASSWORD = "1234"


def get_initial_admin_password() -> str:
    return os.getenv(INITIAL_ADMIN_PASSWORD_ENV, DEFAULT_INITIAL_ADMIN_PASSWORD)


def normalize_default_admin(user: User) -> User:
    user.login_id = DEFAULT_ADMIN_LOGIN_ID
    user.login_id_normalized = DEFAULT_ADMIN_LOGIN_ID
    user.username = DEFAULT_ADMIN_USERNAME
    user.role = DEFAULT_ADMIN_ROLE
    user.status = DEFAULT_ADMIN_STATUS
    if not user.display_name:
        user.display_name = DEFAULT_ADMIN_DISPLAY_NAME
    return user


async def ensure_default_admin(session, *, initial_password: str | None = None) -> tuple[User, bool]:
    existing_admin = await session.scalar(
        select(User).where(
            or_(
                User.login_id_normalized == DEFAULT_ADMIN_LOGIN_ID,
                User.role == DEFAULT_ADMIN_ROLE,
            )
        )
    )

    if existing_admin is not None:
        return normalize_default_admin(existing_admin), False

    admin = User(
        id=uuid.uuid4(),
        login_id=DEFAULT_ADMIN_LOGIN_ID,
        login_id_normalized=DEFAULT_ADMIN_LOGIN_ID,
        username=DEFAULT_ADMIN_USERNAME,
        email=None,
        email_normalized=None,
        department=None,
        display_name=DEFAULT_ADMIN_DISPLAY_NAME,
        role=DEFAULT_ADMIN_ROLE,
        status=DEFAULT_ADMIN_STATUS,
        password_hash=hash_password(initial_password or get_initial_admin_password()),
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )
    session.add(admin)
    return admin, True


async def seed_default_admin(*, initial_password: str | None = None) -> tuple[User, bool]:
    async with AsyncSessionLocal() as session:
        admin, created = await ensure_default_admin(session, initial_password=initial_password)
        await session.commit()
        return admin, created
