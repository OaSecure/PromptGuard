import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import utc_now
from app.db.session import get_db_session
from app.models.auth import User
from app.models.filters import FilterRule
from app.routes.dashboard_session import require_dashboard_admin_mutation, require_dashboard_admin_session
from app.routes.filters import (
    CUSTOM_EDITABLE_FIELDS,
    FilterRuleCreateRequest,
    FilterRulePatchRequest,
    _get_rule,
)
from app.routes.analyze import risk_level_for_score
from app.services.filter_rules import RuleMatch, evaluate_filter_rules, score_for_matches

router = APIRouter(prefix="/dashboard/filters", tags=["dashboard-filters"])
MAX_DRY_RUN_SAMPLE_LENGTH = 20_000

ALLOWED_BUILT_IN_FIELDS = {"enabled", "severity", "action"}
FORBIDDEN_BUILT_IN_FIELDS = {
    "label",
    "keyword",
    "pattern",
    "config_json",
    "placeholder",
    "kind",
    "origin",
    "source",
    "category",
    "detector_key",
}


class DashboardFilterRuleResponse(BaseModel):
    id: uuid.UUID
    origin: str
    kind: str
    category: str
    label: str
    description: str | None
    placeholder: str | None
    severity: str
    action: str
    enabled: bool
    editable_fields: dict[str, Any]
    config_json: dict[str, Any] | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class DashboardDryRunRequest(BaseModel):
    sample_text: str = Field(min_length=1)
    rule_id: uuid.UUID | None = None
    draft_rule: FilterRuleCreateRequest | None = None

    @field_validator("sample_text")
    @classmethod
    def sample_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sample_text must not be blank")
        return value


class DashboardDryRunResponse(BaseModel):
    matched: bool
    expected_action: str
    expected_severity: str
    match_count: int
    reason_code: str
    matched_keywords: list[str]
    evidence_counts: dict[str, int]
    sample_persisted: bool = False


def _dashboard_response(rule: FilterRule) -> DashboardFilterRuleResponse:
    return DashboardFilterRuleResponse(
        id=rule.id,
        origin=rule.origin,
        kind=rule.kind,
        category=rule.category,
        label=rule.label,
        description=rule.description,
        placeholder=rule.placeholder,
        severity=rule.severity,
        action=rule.action,
        enabled=rule.enabled,
        editable_fields=rule.editable_fields,
        config_json=rule.config_json,
        created_at=getattr(rule, "created_at", None),
        updated_at=getattr(rule, "updated_at", None),
        archived_at=rule.archived_at,
    )


def _validate_context_config(config_json: dict[str, Any] | None) -> None:
    if not config_json:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="context_rule config_json is required")
    groups = config_json.get("keyword_groups")
    exclusions = config_json.get("exclusion_keywords")
    window_size = config_json.get("window_size")
    min_condition_count = config_json.get("min_condition_count")
    sensitivity = config_json.get("sensitivity")
    if not isinstance(groups, dict) or not groups:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="keyword_groups is required")
    if exclusions is not None and not isinstance(exclusions, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="exclusion_keywords must be a list")
    if not isinstance(window_size, int) or window_size <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="window_size must be positive")
    if not isinstance(min_condition_count, int) or min_condition_count <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="min_condition_count must be positive")
    if sensitivity not in {"low", "medium", "high"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="sensitivity is invalid")


def _validate_dashboard_create(payload: FilterRuleCreateRequest) -> None:
    if payload.kind == "regex":
        pattern = payload.pattern or (payload.config_json or {}).get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="pattern is required")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="pattern is invalid") from exc
    if payload.kind == "context_rule":
        _validate_context_config(payload.config_json)
    if payload.kind == "keyword":
        keywords = (payload.config_json or {}).get("keywords")
        if not payload.keyword and not (isinstance(keywords, list) and keywords):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="keyword is required")


def _dashboard_rule_from_create(payload: FilterRuleCreateRequest, admin: User) -> FilterRule:
    _validate_dashboard_create(payload)
    pattern = payload.pattern
    keyword = payload.keyword
    if payload.kind == "regex" and not pattern and isinstance(payload.config_json, dict):
        value = payload.config_json.get("pattern")
        pattern = value if isinstance(value, str) else None
    if payload.kind == "keyword" and not keyword and isinstance(payload.config_json, dict):
        values = payload.config_json.get("keywords")
        if isinstance(values, list) and values and isinstance(values[0], str):
            keyword = values[0]
    return FilterRule(
        id=uuid.uuid4(),
        origin="custom",
        kind=payload.kind,
        category=payload.category,
        label=payload.label,
        description=payload.description,
        keyword=keyword,
        pattern=pattern,
        placeholder=payload.placeholder,
        severity=payload.severity,
        action=payload.action,
        enabled=payload.enabled,
        editable_fields=CUSTOM_EDITABLE_FIELDS,
        config_json=payload.config_json,
        version=1,
        created_by_user_id=admin.id,
        updated_by_user_id=admin.id,
    )


def _reject_forbidden_built_in_update(rule: FilterRule, updates: dict[str, Any]) -> None:
    if rule.origin != "built_in":
        return
    forbidden = FORBIDDEN_BUILT_IN_FIELDS.intersection(updates)
    disallowed = set(updates).difference(ALLOWED_BUILT_IN_FIELDS)
    if forbidden or disallowed:
        field = sorted(forbidden or disallowed)[0]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{field} is not editable")


@router.get("", response_model=list[DashboardFilterRuleResponse])
async def list_dashboard_filters(
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> list[DashboardFilterRuleResponse]:
    del current_admin
    result = await session.execute(
        select(FilterRule).where(FilterRule.archived_at.is_(None)).order_by(FilterRule.origin.asc(), FilterRule.kind.asc(), FilterRule.label.asc())
    )
    return [_dashboard_response(rule) for rule in result.scalars().all()]


@router.get("/{rule_id}", response_model=DashboardFilterRuleResponse)
async def get_dashboard_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardFilterRuleResponse:
    del current_admin
    return _dashboard_response(await _get_rule(session, rule_id))


@router.post("", response_model=DashboardFilterRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard_filter(
    payload: FilterRuleCreateRequest,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardFilterRuleResponse:
    rule = _dashboard_rule_from_create(payload, current_admin)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return _dashboard_response(rule)


@router.patch("/{rule_id}", response_model=DashboardFilterRuleResponse)
async def update_dashboard_filter(
    rule_id: uuid.UUID,
    payload: FilterRulePatchRequest,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardFilterRuleResponse:
    rule = await _get_rule(session, rule_id)
    updates = payload.model_dump(exclude_unset=True)
    _reject_forbidden_built_in_update(rule, updates)
    for field in updates:
        if not rule.editable_fields.get(field):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{field} is not editable")
    next_config = updates.get("config_json", rule.config_json)
    if rule.kind == "context_rule":
        _validate_context_config(next_config)
    if rule.kind == "regex":
        pattern = updates.get("pattern", rule.pattern)
        if isinstance(next_config, dict) and not pattern:
            pattern = next_config.get("pattern")
        if not isinstance(pattern, str):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="pattern is required")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="pattern is invalid") from exc
    for field, value in updates.items():
        setattr(rule, field, value)
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    await session.refresh(rule)
    return _dashboard_response(rule)


@router.patch("/{rule_id}/enable", response_model=DashboardFilterRuleResponse)
async def enable_dashboard_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardFilterRuleResponse:
    return await _set_dashboard_enabled(rule_id, True, current_admin, session)


@router.patch("/{rule_id}/disable", response_model=DashboardFilterRuleResponse)
async def disable_dashboard_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardFilterRuleResponse:
    return await _set_dashboard_enabled(rule_id, False, current_admin, session)


async def _set_dashboard_enabled(rule_id: uuid.UUID, enabled: bool, current_admin: User, session: AsyncSession) -> DashboardFilterRuleResponse:
    rule = await _get_rule(session, rule_id)
    rule.enabled = enabled
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    await session.refresh(rule)
    return _dashboard_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_dashboard_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    rule = await _get_rule(session, rule_id)
    if rule.origin == "built_in":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="built-in rules cannot be archived")
    rule.archived_at = utc_now()
    rule.enabled = False
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    return None


def _safe_keywords(rule: FilterRule, match: RuleMatch) -> list[str]:
    config = rule.config_json or {}
    if rule.kind == "keyword":
        values = config.get("keywords")
        if isinstance(values, list):
            return [item for item in values if isinstance(item, str)]
        return [rule.keyword] if rule.keyword else []
    if rule.kind == "context_rule":
        groups = config.get("keyword_groups")
        if isinstance(groups, dict):
            return [key for key in groups if isinstance(key, str)]
    if match.source != "custom_regex":
        return [rule.label]
    return []


def _dry_run_response(rule: FilterRule, matches: list[RuleMatch]) -> DashboardDryRunResponse:
    match = matches[0] if matches else None
    score = score_for_matches(matches)
    return DashboardDryRunResponse(
        matched=match is not None,
        expected_action=match.action if match else "ALLOW",
        expected_severity=match.severity if match else "low",
        match_count=match.match_count if match else 0,
        reason_code=match.reason_code if match else "NO_MATCH",
        matched_keywords=_safe_keywords(rule, match) if match else [],
        evidence_counts={"matches": match.match_count if match else 0, "risk_score": score, "risk_level": 1 if matches else 0},
        sample_persisted=False,
    )


@router.post("/dry-run", response_model=DashboardDryRunResponse)
async def dry_run_dashboard_filter(
    payload: DashboardDryRunRequest,
    current_admin: User = Depends(require_dashboard_admin_mutation),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardDryRunResponse:
    del current_admin
    if len(payload.sample_text) > MAX_DRY_RUN_SAMPLE_LENGTH:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="dry-run sample is too large")
    if payload.rule_id is not None:
        rule = await _get_rule(session, payload.rule_id)
    elif payload.draft_rule is not None:
        rule = _dashboard_rule_from_create(payload.draft_rule, User(id=uuid.uuid4()))  # type: ignore[call-arg]
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="rule_id or draft_rule is required")
    matches = evaluate_filter_rules(payload.sample_text, [rule])
    return _dry_run_response(rule, matches)
