import re
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.core.tokens import utc_now
from app.models.auth import User
from app.models.filters import FilterRule
from app.routes.auth import require_admin
from app.services.filter_rules import (
    action_for_matches,
    evaluate_filter_rules,
    filter_rule_set_version,
    load_active_filter_rules,
    score_for_matches,
)
from app.routes.analyze import risk_level_for_score

router = APIRouter(prefix="/filters", tags=["filters"])

RuleKind = Literal["detector", "keyword", "regex", "context_rule"]
RuleSeverity = Literal["low", "medium", "high", "critical"]
RuleAction = Literal["ALLOW", "WARN", "MASK", "BLOCK"]

CUSTOM_EDITABLE_FIELDS = {
    "category": True,
    "label": True,
    "description": True,
    "keyword": True,
    "pattern": True,
    "placeholder": True,
    "severity": True,
    "action": True,
    "enabled": True,
    "config_json": True,
}


class FilterRuleCreateRequest(BaseModel):
    kind: Literal["keyword", "regex", "context_rule"]
    category: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    keyword: str | None = Field(default=None, min_length=1, max_length=255)
    pattern: str | None = Field(default=None, min_length=1, max_length=1000)
    placeholder: str | None = Field(default=None, min_length=1, max_length=80)
    severity: RuleSeverity = "medium"
    action: RuleAction = "MASK"
    enabled: bool = True
    config_json: dict[str, Any] | None = None

    @field_validator("category", "label", "description", "keyword", "pattern", "placeholder")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FilterRulePatchRequest(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    label: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    keyword: str | None = Field(default=None, min_length=1, max_length=255)
    pattern: str | None = Field(default=None, min_length=1, max_length=1000)
    placeholder: str | None = Field(default=None, min_length=1, max_length=80)
    severity: RuleSeverity | None = None
    action: RuleAction | None = None
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None

    @field_validator("category", "label", "description", "keyword", "pattern", "placeholder")
    @classmethod
    def strip_patch_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FilterDryRunRequest(BaseModel):
    sample_text: str = Field(min_length=1, max_length=20_000)

    @field_validator("sample_text")
    @classmethod
    def sample_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sample_text must not be blank")
        return value


class FilterRuleResponse(BaseModel):
    id: uuid.UUID
    origin: str
    kind: str
    category: str
    label: str
    description: str | None
    detector_key: str | None
    keyword: str | None
    pattern: str | None
    placeholder: str | None
    severity: str
    action: str
    enabled: bool
    editable_fields: dict[str, Any]
    config_json: dict[str, Any] | None
    version: int
    archived_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DryRunDetection(BaseModel):
    category: str
    type: str
    source: str
    severity: str
    confidence: int
    count: int
    reason_code: str
    match_count: int
    safe_evidence: dict[str, Any]


class FilterDryRunResponse(BaseModel):
    matched: bool
    expected_action: str
    risk_score: int
    risk_level: str
    filter_rule_set_version: str
    detections: list[DryRunDetection]


def _rule_response(rule: FilterRule) -> FilterRuleResponse:
    return FilterRuleResponse(
        id=rule.id,
        origin=rule.origin,
        kind=rule.kind,
        category=rule.category,
        label=rule.label,
        description=rule.description,
        detector_key=rule.detector_key,
        keyword=rule.keyword,
        pattern=rule.pattern,
        placeholder=rule.placeholder,
        severity=rule.severity,
        action=rule.action,
        enabled=rule.enabled,
        editable_fields=rule.editable_fields,
        config_json=rule.config_json,
        version=rule.version,
        archived_at=rule.archived_at,
        created_at=getattr(rule, "created_at", None),
        updated_at=getattr(rule, "updated_at", None),
    )


def _validate_rule_shape(kind: str, keyword: str | None, pattern: str | None, config_json: dict[str, Any] | None) -> None:
    configured_keywords = (config_json or {}).get("keywords")
    has_configured_keywords = isinstance(configured_keywords, list) and any(
        isinstance(item, str) and item.strip() for item in configured_keywords
    )
    if kind == "keyword" and not keyword and not has_configured_keywords:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="keyword is required")
    if kind == "regex":
        if not pattern:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pattern is required")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pattern is invalid") from exc
    if kind == "context_rule" and not isinstance(config_json, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config_json is required")


async def _get_rule(session: AsyncSession, rule_id: uuid.UUID) -> FilterRule:
    rule = await session.get(FilterRule, rule_id)
    if rule is None or rule.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="filter rule not found")
    return rule


@router.get("", response_model=list[FilterRuleResponse])
async def list_filters(
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[FilterRuleResponse]:
    del current_admin
    result = await session.execute(
        select(FilterRule).where(FilterRule.archived_at.is_(None)).order_by(FilterRule.origin.asc(), FilterRule.kind.asc(), FilterRule.label.asc())
    )
    return [_rule_response(rule) for rule in result.scalars().all()]




@router.get("/{rule_id}", response_model=FilterRuleResponse)
async def get_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterRuleResponse:
    del current_admin
    return _rule_response(await _get_rule(session, rule_id))


@router.post("", response_model=FilterRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_filter(
    payload: FilterRuleCreateRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterRuleResponse:
    _validate_rule_shape(payload.kind, payload.keyword, payload.pattern, payload.config_json)
    rule = FilterRule(
        id=uuid.uuid4(),
        origin="custom",
        kind=payload.kind,
        category=payload.category,
        label=payload.label,
        description=payload.description,
        keyword=payload.keyword,
        pattern=payload.pattern,
        placeholder=payload.placeholder,
        severity=payload.severity,
        action=payload.action,
        enabled=payload.enabled,
        editable_fields=CUSTOM_EDITABLE_FIELDS,
        config_json=payload.config_json,
        version=1,
        created_by_user_id=current_admin.id,
        updated_by_user_id=current_admin.id,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return _rule_response(rule)


@router.patch("/{rule_id}", response_model=FilterRuleResponse)
async def update_filter(
    rule_id: uuid.UUID,
    payload: FilterRulePatchRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterRuleResponse:
    rule = await _get_rule(session, rule_id)
    updates = payload.model_dump(exclude_unset=True)
    for field in updates:
        if not rule.editable_fields.get(field):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} is not editable")

    next_keyword = updates.get("keyword", rule.keyword)
    next_pattern = updates.get("pattern", rule.pattern)
    next_config = updates.get("config_json", rule.config_json)
    _validate_rule_shape(rule.kind, next_keyword, next_pattern, next_config)

    for field, value in updates.items():
        setattr(rule, field, value)
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    await session.refresh(rule)
    return _rule_response(rule)


@router.patch("/{rule_id}/enable", response_model=FilterRuleResponse)
async def enable_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterRuleResponse:
    return await _set_enabled(rule_id, True, current_admin, session)


@router.patch("/{rule_id}/disable", response_model=FilterRuleResponse)
async def disable_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterRuleResponse:
    return await _set_enabled(rule_id, False, current_admin, session)


async def _set_enabled(rule_id: uuid.UUID, enabled: bool, current_admin: User, session: AsyncSession) -> FilterRuleResponse:
    rule = await _get_rule(session, rule_id)
    if not rule.editable_fields.get("enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="enabled is not editable")
    rule.enabled = enabled
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    await session.refresh(rule)
    return _rule_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_filter(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    rule = await _get_rule(session, rule_id)
    if rule.origin == "built_in":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="built-in rules cannot be archived")
    rule.archived_at = utc_now()
    rule.version += 1
    rule.updated_by_user_id = current_admin.id
    await session.commit()
    return None


@router.post("/dry-run", response_model=FilterDryRunResponse)
async def dry_run_filter(
    payload: FilterDryRunRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FilterDryRunResponse:
    del current_admin
    rules = await load_active_filter_rules(session)
    matches = evaluate_filter_rules(payload.sample_text, rules)
    score = score_for_matches(matches)
    return FilterDryRunResponse(
        matched=bool(matches),
        expected_action=action_for_matches(matches),
        risk_score=score,
        risk_level=risk_level_for_score(score),
        filter_rule_set_version=filter_rule_set_version(rules),
        detections=[
            DryRunDetection(
                category=match.category,
                type=match.type,
                source=match.source,
                severity=match.severity,
                confidence=match.confidence,
                count=match.count,
                reason_code=match.reason_code,
                match_count=match.match_count,
                safe_evidence=match.safe_evidence,
            )
            for match in matches
        ],
    )
