from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.types.policy import ConfigurablePolicyAction, PolicyActionSettings, UnsupportedMaskFallbackAction
from app.models.policy_settings import PolicySettings

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


def policy_action_settings_from_row(row: PolicySettings | None) -> PolicyActionSettings:
    values = DEFAULT_POLICY_SETTINGS if row is None else {
        "context_classifier_action": row.context_classifier_action,
        "content_not_scanned_action": row.content_not_scanned_action,
        "parser_or_ocr_failure_action": row.parser_or_ocr_failure_action,
        "empty_input_action": row.empty_input_action,
        "unsupported_mask_fallback_action": row.unsupported_mask_fallback_action,
    }
    return PolicyActionSettings(
        context_classifier_action=_canonical_action(values["context_classifier_action"]),
        content_not_scanned_action=_canonical_action(values["content_not_scanned_action"]),
        parser_or_ocr_failure_action=_canonical_action(values["parser_or_ocr_failure_action"]),
        empty_input_action=_canonical_action(values["empty_input_action"]),
        unsupported_mask_fallback_action=_canonical_fallback_action(values["unsupported_mask_fallback_action"]),
    )


def _canonical_action(action: str) -> ConfigurablePolicyAction:
    return cast(ConfigurablePolicyAction, action.lower())


def _canonical_fallback_action(action: str) -> UnsupportedMaskFallbackAction:
    return cast(UnsupportedMaskFallbackAction, action.lower())
