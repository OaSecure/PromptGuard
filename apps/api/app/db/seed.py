from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth import User
from app.models.filters import FilterRule


DEFAULT_ADMIN_LOGIN_ID = "admin"
DEFAULT_ADMIN_LOGIN_ID_NORMALIZED = "admin"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_DISPLAY_NAME = "PromptGuard Admin"
BUILT_IN_DETECTOR_RULES = [
    {
        "id": "00000000-0000-4000-8000-000000000101",
        "origin": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Email Address",
        "description": "Detects email address patterns.",
        "detector_key": "EMAIL",
        "placeholder": "EMAIL",
        "severity": "medium",
        "action": "MASK",
    },
    {
        "id": "00000000-0000-4000-8000-000000000102",
        "origin": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Phone Number",
        "description": "Detects Korean phone number patterns.",
        "detector_key": "PHONE",
        "placeholder": "PHONE",
        "severity": "medium",
        "action": "MASK",
    },
    {
        "id": "00000000-0000-4000-8000-000000000103",
        "origin": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Resident Registration Number",
        "description": "Detects valid dummy resident registration numbers.",
        "detector_key": "RRN",
        "placeholder": "RRN",
        "severity": "high",
        "action": "MASK",
    },
    {
        "id": "00000000-0000-4000-8000-000000000104",
        "origin": "built_in",
        "kind": "detector",
        "category": "Payment",
        "label": "Card Number",
        "description": "Detects Luhn-valid card numbers.",
        "detector_key": "CARD",
        "placeholder": "CARD",
        "severity": "high",
        "action": "MASK",
    },
]
BUILT_IN_EDITABLE_FIELDS = {"severity": True, "action": True, "enabled": True}


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
            await ensure_builtin_filter_rules(session)


async def ensure_builtin_filter_rules(session: AsyncSession) -> int:
    created_count = 0
    for definition in BUILT_IN_DETECTOR_RULES:
        result = await session.execute(
            select(FilterRule).where(
                FilterRule.origin == "built_in",
                FilterRule.kind == "detector",
                FilterRule.detector_key == definition["detector_key"],
            )
        )
        if result.scalar_one_or_none() is not None:
            continue
        values = {key: value for key, value in definition.items() if key != "id"}
        rule = FilterRule(
            **values,
            id=uuid.UUID(definition["id"]),
            enabled=True,
            editable_fields=BUILT_IN_EDITABLE_FIELDS,
            config_json={},
            version=1,
        )
        session.add(rule)
        created_count += 1
    if created_count:
        await session.flush()
    return created_count


def main() -> None:
    asyncio.run(seed_initial_data())


if __name__ == "__main__":
    main()
