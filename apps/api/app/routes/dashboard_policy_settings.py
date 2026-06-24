import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.events import AuditLog
from app.models.policy_settings import PolicySettings
from app.routes.dashboard_session import require_dashboard_admin_mutation, require_dashboard_admin_session
from app.services.policy_settings import (
    DEFAULT_POLICY_SETTINGS,
    get_or_create_policy_settings_row,
    get_policy_settings_row,
)

router = APIRouter(prefix="/dashboard/policy-settings", tags=["dashboard-policy-settings"])

ConfigurablePolicyAction = Literal["ALLOW", "WARN", "BLOCK"]
UnsupportedMaskFallbackAction = Literal["WARN", "BLOCK"]


class DashboardPolicySettingsResponse(BaseModel):
    context_classifier_action: ConfigurablePolicyAction
    content_not_scanned_action: ConfigurablePolicyAction
    parser_or_ocr_failure_action: ConfigurablePolicyAction
    empty_input_action: ConfigurablePolicyAction
    unsupported_mask_fallback_action: UnsupportedMaskFallbackAction
    version: int


class DashboardPolicySettingsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_classifier_action: ConfigurablePolicyAction | None = None
    content_not_scanned_action: ConfigurablePolicyAction | None = None
    parser_or_ocr_failure_action: ConfigurablePolicyAction | None = None
    empty_input_action: ConfigurablePolicyAction | None = None
    unsupported_mask_fallback_action: UnsupportedMaskFallbackAction | None = None


def _response_from_row(row: PolicySettings | None) -> DashboardPolicySettingsResponse:
    if row is None:
        return DashboardPolicySettingsResponse(
            context_classifier_action=cast(ConfigurablePolicyAction, DEFAULT_POLICY_SETTINGS["context_classifier_action"]),
            content_not_scanned_action=cast(ConfigurablePolicyAction, DEFAULT_POLICY_SETTINGS["content_not_scanned_action"]),
            parser_or_ocr_failure_action=cast(ConfigurablePolicyAction, DEFAULT_POLICY_SETTINGS["parser_or_ocr_failure_action"]),
            empty_input_action=cast(ConfigurablePolicyAction, DEFAULT_POLICY_SETTINGS["empty_input_action"]),
            unsupported_mask_fallback_action=cast(
                UnsupportedMaskFallbackAction,
                DEFAULT_POLICY_SETTINGS["unsupported_mask_fallback_action"],
            ),
            version=0,
        )
    return DashboardPolicySettingsResponse(
        context_classifier_action=cast(ConfigurablePolicyAction, row.context_classifier_action),
        content_not_scanned_action=cast(ConfigurablePolicyAction, row.content_not_scanned_action),
        parser_or_ocr_failure_action=cast(ConfigurablePolicyAction, row.parser_or_ocr_failure_action),
        empty_input_action=cast(ConfigurablePolicyAction, row.empty_input_action),
        unsupported_mask_fallback_action=cast(UnsupportedMaskFallbackAction, row.unsupported_mask_fallback_action),
        version=row.version,
    )


def _safe_audit_metadata(row: PolicySettings, changed_fields: set[str]) -> dict[str, Any]:
    return {
        "settings_key": row.settings_key,
        "version": row.version,
        "changed_fields": sorted(changed_fields),
        "context_classifier_action": row.context_classifier_action,
        "content_not_scanned_action": row.content_not_scanned_action,
        "parser_or_ocr_failure_action": row.parser_or_ocr_failure_action,
        "empty_input_action": row.empty_input_action,
        "unsupported_mask_fallback_action": row.unsupported_mask_fallback_action,
    }


@router.get("", response_model=DashboardPolicySettingsResponse)
async def get_dashboard_policy_settings(
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardPolicySettingsResponse:
    del current_admin
    return _response_from_row(await get_policy_settings_row(session))


@router.patch("", response_model=DashboardPolicySettingsResponse)
async def update_dashboard_policy_settings(
    payload: DashboardPolicySettingsPatchRequest,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardPolicySettingsResponse:
    updates = payload.model_dump(exclude_unset=True)
    row = await get_or_create_policy_settings_row(session)
    changed_fields: set[str] = set()
    for field, value in updates.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed_fields.add(field)
    row.version += 1
    row.updated_by_user_id = current_admin.id
    session.add(
        AuditLog(
            actor_login_id=_actor_login_id(current_admin),
            action="policy_settings.update",
            target_type="policy_settings",
            target_id=row.settings_key,
            safe_metadata=_safe_audit_metadata(row, changed_fields),
        )
    )
    await session.commit()
    await session.refresh(row)
    return _response_from_row(row)


def _actor_login_id(current_admin: User) -> str:
    value = getattr(current_admin, "login_id", None)
    if isinstance(value, str) and value:
        return value
    user_id = getattr(current_admin, "id", None)
    if isinstance(user_id, uuid.UUID):
        return str(user_id)
    return "dashboard-admin"
