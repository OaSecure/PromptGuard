import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompt_hash import compute_prompt_hash
from app.core.tokens import utc_now
from app.masking.placeholder import apply_placeholders
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection, EventInput
from app.routes.auth import get_db_session, require_active_user
from app.services.filter_rules import (
    RuleMatch,
    action_for_matches,
    detections_for_masking,
    evaluate_filter_rules,
    filter_rule_set_version,
    load_active_filter_rules,
    score_for_matches,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])

MAX_PROMPT_LENGTH = 20_000
MAX_CONTEXT_JSON_LENGTH = 4_096
ACTION_ALLOW = "ALLOW"
ACTION_MASK = "MASK"


class AnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    context: dict[str, Any] = Field(default_factory=dict)
    filter_config_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    client_request_id: uuid.UUID | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("context")
    @classmethod
    def context_must_be_bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("context must be JSON serializable") from exc

        if len(encoded) > MAX_CONTEXT_JSON_LENGTH:
            raise ValueError("context is too large")
        return value


class WorkspaceContext(BaseModel):
    source: Literal["authenticated_user"]
    user_id: uuid.UUID


class AnalyzeDetection(BaseModel):
    category: str
    type: str
    source: str
    severity: Literal["low", "medium", "high", "critical"]
    confidence: int
    count: int
    reason_code: str
    match_count: int


class AnalyzeResponse(BaseModel):
    event_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["accepted"]
    action: Literal["ALLOW", "WARN", "MASK", "BLOCK"]
    checked_at: datetime
    risk_score: int
    risk_level: Literal["low", "medium", "high", "critical"]
    user_message: str
    allow_original_send: bool
    requires_justification: bool
    detections: list[AnalyzeDetection]
    prompt_length: int
    client_request_id: uuid.UUID | None
    filter_config_version: str | None
    workspace_context: WorkspaceContext
    masked_prompt: str | None = None


def safe_context_string(context: dict[str, Any], key: str, max_length: int) -> str | None:
    value = context.get(key)
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None
    return value[:max_length]


def risk_level_for_score(score: int) -> Literal["low", "medium", "high", "critical"]:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def response_detections(matches: list[RuleMatch]) -> list[AnalyzeDetection]:
    return [
        AnalyzeDetection(
            category=match.category,
            type=match.type,
            source=match.source,
            severity=match.severity,
            confidence=match.confidence,
            count=match.count,
            reason_code=match.reason_code,
            match_count=match.match_count,
        )
        for match in matches
    ]


def event_input_row(event_id: uuid.UUID, prompt: str, matches: list[RuleMatch]) -> EventInput:
    return EventInput(
        id=uuid.uuid4(),
        event_id=event_id,
        input_id="composer",
        input_index=0,
        kind="text",
        source="composer",
        size_bytes=len(prompt.encode("utf-8")),
        content_included=True,
        content_scanned=True,
        decision_basis="detection" if matches else "no_detection",
        content_unavailable_reason=None,
        limit_exceeded=None,
    )


def event_detection_rows(event_id: uuid.UUID, matches: list[RuleMatch]) -> list[EventDetection]:
    rows: list[EventDetection] = []
    for match in matches:
        rows.append(
            EventDetection(
                id=uuid.uuid4(),
                event_id=event_id,
                input_id="composer",
                input_index=0,
                kind="text",
                category=match.category,
                type=match.type,
                source="composer",
                filter_rule_id=match.rule_id,
                detector_id=match.source,
                action=match.action,
                placeholder=match.placeholder,
                severity=match.severity,
                confidence=match.confidence,
                count=match.count,
                reason_code=match.reason_code,
                match_count=match.match_count,
                matched_keywords=[],
                evidence_counts={"match_count": match.match_count},
                safe_evidence=match.safe_evidence,
            )
        )
    return rows


def user_message_for_action(action: str) -> str:
    if action == ACTION_MASK:
        return "Sensitive data was detected and replaced with placeholders."
    if action == "WARN":
        return "Sensitive or governed content was detected. Review before sending."
    if action == "BLOCK":
        return "Sensitive or governed content was detected and should not be sent."
    return "No sensitive data was detected."


@router.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
async def analyze_prompt(
    payload: AnalyzeRequest,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyzeResponse:
    request_id = uuid.uuid4()
    event_id = uuid.uuid4()
    checked_at = utc_now()
    rules = await load_active_filter_rules(session)
    matches = evaluate_filter_rules(payload.prompt, rules)
    risk_score = score_for_matches(matches)
    action = action_for_matches(matches)
    risk_level = risk_level_for_score(risk_score)
    masking_detections = detections_for_masking(matches)
    masked = apply_placeholders(payload.prompt, masking_detections) if action == ACTION_MASK and masking_detections else None
    active_filter_rule_set_version = payload.filter_config_version or filter_rule_set_version(rules)
    prompt_hash = compute_prompt_hash(workspace_id=str(current_user.id), prompt=payload.prompt)

    event = AnalysisEvent(
        id=event_id,
        user_id=current_user.id,
        login_id=getattr(current_user, "login_id", None),
        client_request_id=payload.client_request_id,
        prompt_hash=prompt_hash.digest,
        prompt_hash_key_id=prompt_hash.key_id,
        action=action,
        risk_score=risk_score,
        risk_level=risk_level,
        filter_rule_set_version=active_filter_rule_set_version,
        service=safe_context_string(payload.context, "service", 120),
        service_domain=safe_context_string(payload.context, "service_domain", 255),
        platform=safe_context_string(payload.context, "platform", 120),
    )
    session.add(event)
    session.add(event_input_row(event_id, payload.prompt, matches))
    for row in event_detection_rows(event_id, matches):
        session.add(row)

    current_user.last_event_at = checked_at
    await session.commit()

    return AnalyzeResponse(
        event_id=event_id,
        request_id=request_id,
        status="accepted",
        action=action,
        checked_at=checked_at,
        risk_score=risk_score,
        risk_level=risk_level,
        user_message=user_message_for_action(action),
        allow_original_send=action == ACTION_ALLOW,
        requires_justification=False,
        detections=response_detections(matches),
        prompt_length=len(payload.prompt),
        client_request_id=payload.client_request_id,
        filter_config_version=active_filter_rule_set_version,
        workspace_context=WorkspaceContext(source="authenticated_user", user_id=current_user.id),
        masked_prompt=masked.text if masked is not None else None,
    )
