import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompt_hash import compute_prompt_hash
from app.core.tokens import utc_now
from app.detectors.pii import Detection, detect_pii
from app.masking.placeholder import apply_placeholders
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection
from app.routes.auth import get_db_session, require_active_user

router = APIRouter(prefix="/prompts", tags=["prompts"])

MAX_PROMPT_LENGTH = 20_000
MAX_CONTEXT_JSON_LENGTH = 4_096
DEFAULT_FILTER_RULE_SET_VERSION = "built-in:2026-05-30"
SAFE_CONTEXT_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
SAFE_CONTEXT_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")

ACTION_ALLOW = "ALLOW"
ACTION_MASK = "MASK"

DETECTOR_POLICIES = {
    "EMAIL": {"severity": "medium", "score": 55, "action": ACTION_MASK, "reason_code": "PII_EMAIL_DETECTED"},
    "PHONE": {"severity": "medium", "score": 55, "action": ACTION_MASK, "reason_code": "PII_PHONE_DETECTED"},
    "RRN": {"severity": "high", "score": 80, "action": ACTION_MASK, "reason_code": "PII_RRN_DETECTED"},
    "CARD": {"severity": "high", "score": 80, "action": ACTION_MASK, "reason_code": "PAYMENT_CARD_DETECTED"},
}


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
    source: Literal["built_in_detector"]
    severity: Literal["medium", "high"]
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


def safe_context_label(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not SAFE_CONTEXT_LABEL_RE.fullmatch(value):
        return None
    return value


def safe_context_domain(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if not isinstance(value, str):
        return None

    value = value.strip().lower()
    if not SAFE_CONTEXT_DOMAIN_RE.fullmatch(value):
        return None
    return value


def risk_level_for_score(score: int) -> Literal["low", "medium", "high", "critical"]:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def grouped_detections(detections: list[Detection]) -> list[AnalyzeDetection]:
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.detector_key, []).append(detection)

    response_items: list[AnalyzeDetection] = []
    for detector_key in sorted(grouped):
        matches = grouped[detector_key]
        policy = DETECTOR_POLICIES[detector_key]
        response_items.append(
            AnalyzeDetection(
                category=matches[0].category,
                type=detector_key,
                source="built_in_detector",
                severity=policy["severity"],
                confidence=100,
                count=len(matches),
                reason_code=policy["reason_code"],
                match_count=len(matches),
            )
        )
    return response_items


def event_detection_rows(event_id: uuid.UUID, detections: list[Detection]) -> list[EventDetection]:
    rows: list[EventDetection] = []
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.detector_key, []).append(detection)

    for detector_key in sorted(grouped):
        matches = grouped[detector_key]
        policy = DETECTOR_POLICIES[detector_key]
        rows.append(
            EventDetection(
                id=uuid.uuid4(),
                event_id=event_id,
                category=matches[0].category,
                type=detector_key,
                source="built_in_detector",
                severity=policy["severity"],
                confidence=100,
                count=len(matches),
                reason_code=policy["reason_code"],
                match_count=len(matches),
                safe_evidence={"value_lengths": [item.value_length for item in matches]},
            )
        )
    return rows


def score_for_detections(detections: list[Detection]) -> int:
    if not detections:
        return 0
    return max(DETECTOR_POLICIES[item.detector_key]["score"] for item in detections)


def action_for_detections(detections: list[Detection]) -> Literal["ALLOW", "MASK"]:
    if not detections:
        return ACTION_ALLOW
    return ACTION_MASK


def user_message_for_action(action: str) -> str:
    if action == ACTION_MASK:
        return "Sensitive data was detected and replaced with placeholders."
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
    detections = detect_pii(payload.prompt)
    risk_score = score_for_detections(detections)
    action = action_for_detections(detections)
    risk_level = risk_level_for_score(risk_score)
    masked = apply_placeholders(payload.prompt, detections) if action == ACTION_MASK else None
    filter_rule_set_version = payload.filter_config_version or DEFAULT_FILTER_RULE_SET_VERSION
    prompt_hash = compute_prompt_hash(workspace_id=str(current_user.id), prompt=payload.prompt)

    event = AnalysisEvent(
        id=event_id,
        user_id=current_user.id,
        prompt_hash=prompt_hash.digest,
        prompt_hash_key_id=prompt_hash.key_id,
        action=action,
        risk_score=risk_score,
        risk_level=risk_level,
        filter_rule_set_version=filter_rule_set_version,
        service=safe_context_label(payload.context, "service"),
        service_domain=safe_context_domain(payload.context, "service_domain"),
        platform=safe_context_label(payload.context, "platform"),
    )
    session.add(event)
    for row in event_detection_rows(event_id, detections):
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
        detections=grouped_detections(detections),
        prompt_length=len(payload.prompt),
        client_request_id=payload.client_request_id,
        filter_config_version=filter_rule_set_version,
        workspace_context=WorkspaceContext(source="authenticated_user", user_id=current_user.id),
        masked_prompt=masked.text if masked is not None else None,
    )
