from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_settings import PolicySettings

ConfigurablePolicyAction = Literal["ALLOW", "WARN", "BLOCK"]
UnsupportedMaskFallbackAction = Literal["WARN", "BLOCK"]

DEFAULT_POLICY_SETTINGS = {
    "context_classifier_action": "WARN",
    "content_not_scanned_action": "WARN",
    "parser_or_ocr_failure_action": "WARN",
    "empty_input_action": "ALLOW",
    "unsupported_mask_fallback_action": "BLOCK",
}


async def get_policy_settings_row(session: AsyncSession) -> PolicySettings | None:
    result = await session.execute(select(PolicySettings).where(PolicySettings.settings_key == "default"))
    return result.scalars().first()


async def get_or_create_policy_settings_row(session: AsyncSession) -> PolicySettings:
    row = await get_policy_settings_row(session)
    if row is not None:
        return row
    row = PolicySettings(settings_key="default", version=0, **DEFAULT_POLICY_SETTINGS)
    session.add(row)
    return row
