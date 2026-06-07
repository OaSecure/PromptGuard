import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompt_hash import compute_prompt_hash
from app.core.tokens import utc_now
from app.masking.placeholder import apply_placeholders
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection, EventInput
from app.models.filters import FilterRule
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

MAX_ANALYZE_REQUEST_BYTES = 2_097_152
MAX_COMPOSER_TEXT_BYTES = 262_144
MAX_CONVERTED_PASTE_TEXT_BYTES = 1_048_576
MAX_FILE_TEXT_SCAN_BYTES = 1_048_576
SAFE_CONTEXT_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
SAFE_CONTEXT_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
SAFE_INPUT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SAFE_CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_FILTER_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SECRET_LIKE_ID_RE = re.compile(
    r"(?:gh[pousr]_|sk-[A-Za-z0-9]|xox[baprs]-|AKIA[0-9A-Z]|postgres://|mysql://|bearer|private[_-]?key)",
    re.IGNORECASE,
)

ACTION_ALLOW = "ALLOW"
ACTION_WARN = "WARN"
ACTION_MASK = "MASK"
ACTION_BLOCK = "BLOCK"
PUBLIC_ACTIONS = {
    ACTION_ALLOW: "Allow",
    ACTION_WARN: "Warn",
    ACTION_MASK: "Mask",
    ACTION_BLOCK: "Block",
}

TEXT_SOURCES = ("composer", "converted_paste", "file")
CONTENT_UNAVAILABLE_REASONS = ("oversized", "unsupported", "metadata_only", "unavailable")
LIMIT_EXCEEDED_CODES = (
    "MAX_ANALYZE_REQUEST_BYTES",
    "MAX_COMPOSER_TEXT_BYTES",
    "MAX_CONVERTED_PASTE_TEXT_BYTES",
    "MAX_FILE_TEXT_SCAN_BYTES",
)
TEXT_SOURCE_LIMITS = {
    "composer": MAX_COMPOSER_TEXT_BYTES,
    "converted_paste": MAX_CONVERTED_PASTE_TEXT_BYTES,
    "file": MAX_FILE_TEXT_SCAN_BYTES,
}
FORBIDDEN_METADATA_KEYS = {"name", "filename", "file_name", "original_filename", "path", "url"}


class AnalyzeRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            body = await request.body()
            if len(body) > MAX_ANALYZE_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Analyze request body is too large"},
                )
            return await original_route_handler(request)

        return custom_route_handler


router.route_class = AnalyzeRoute


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128, pattern=SAFE_CLIENT_REQUEST_ID_RE.pattern)
    filter_config_revision: str = Field(min_length=1, max_length=80, pattern=SAFE_FILTER_REVISION_RE.pattern)
    context: "AnalyzeContext"
    inputs: list["AnalyzeInput"] = Field(min_length=1, max_length=20)

    @field_validator("client_request_id", "filter_config_revision")
    @classmethod
    def id_fields_must_not_look_like_secrets(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("id field must not contain secret-like values")
        return value

    @field_validator("inputs")
    @classmethod
    def input_ids_must_be_unique(cls, value: list["AnalyzeInput"]) -> list["AnalyzeInput"]:
        input_ids = [item.input_id for item in value]
        if len(set(input_ids)) != len(input_ids):
            raise ValueError("input_id values must be unique")
        return value


class AnalyzeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_service: str = Field(min_length=1, max_length=32, pattern=SAFE_CONTEXT_LABEL_RE.pattern)
    ai_service_domain: str = Field(min_length=1, max_length=255, pattern=SAFE_CONTEXT_DOMAIN_RE.pattern)
    page_url_origin: str = Field(min_length=1, max_length=255, pattern=r"^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$")
    extension_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    browser: str = Field(min_length=1, max_length=32, pattern=SAFE_CONTEXT_LABEL_RE.pattern)
    locale: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(min_length=1, max_length=80, pattern=SAFE_INPUT_ID_RE.pattern)
    kind: Literal["text", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "file", "attachment_chip"]
    size_bytes: int = Field(ge=0, le=2_147_483_647)
    content_included: bool
    content: str | None = Field(default=None, max_length=1_048_576)
    metadata: dict[str, Any] | None = None
    content_unavailable_reason: Literal["oversized", "unsupported", "metadata_only", "unavailable"] | None = None
    limit_exceeded: Literal[
        "MAX_ANALYZE_REQUEST_BYTES",
        "MAX_COMPOSER_TEXT_BYTES",
        "MAX_CONVERTED_PASTE_TEXT_BYTES",
        "MAX_FILE_TEXT_SCAN_BYTES",
    ] | None = None

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_look_like_secret(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("input_id must not contain secret-like values")
        return value

    @model_validator(mode="after")
    def validate_input_contract(self) -> "AnalyzeInput":
        if self.kind == "text":
            if self.source not in TEXT_SOURCES:
                raise ValueError("text input source must be composer, converted_paste, or file")
            if self.content_included:
                if self.content is None or not self.content.strip():
                    raise ValueError("included text input must include non-blank content")
                content_size = len(self.content.encode("utf-8"))
                if content_size != self.size_bytes:
                    raise ValueError("size_bytes must equal UTF-8 content byte length")
                if content_size > TEXT_SOURCE_LIMITS[self.source]:
                    raise ValueError("included text input exceeds source byte limit")
                if self.content_unavailable_reason is not None or self.limit_exceeded is not None:
                    raise ValueError("included text input must not include unavailable metadata")
            else:
                if self.content is not None:
                    raise ValueError("content_unavailable text input must not include content")
                if self.content_unavailable_reason is None:
                    raise ValueError("content_unavailable text input must include a reason")
                if self.limit_exceeded is None and self.content_unavailable_reason == "oversized":
                    raise ValueError("oversized text input must include limit_exceeded")
        elif self.kind == "attachment_metadata":
            if self.source != "attachment_chip":
                raise ValueError("attachment_metadata source must be attachment_chip")
            if self.content_included:
                raise ValueError("attachment_metadata content_included must be false")
            if self.content is not None:
                raise ValueError("attachment_metadata must not include content")
            if self.metadata is None:
                raise ValueError("attachment_metadata must include metadata")
            validate_safe_attachment_metadata(self.metadata)
        else:
            if self.source != "attachment_chip":
                raise ValueError("unsupported_attachment source must be attachment_chip")
            if self.content_included:
                raise ValueError("unsupported_attachment content_included must be false")
            if self.content is not None:
                raise ValueError("unsupported_attachment must not include content")
            if self.content_unavailable_reason is None:
                raise ValueError("unsupported_attachment must include a reason")
        return self


def validate_safe_attachment_metadata(metadata: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("attachment metadata must be JSON serializable") from exc

    if len(encoded) > 2_048:
        raise ValueError("attachment metadata is too large")

    for key in unsafe_metadata_keys(metadata):
        if key.casefold() in FORBIDDEN_METADATA_KEYS:
            raise ValueError("attachment metadata must not include original filename, path, or URL")


def unsafe_metadata_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = list(value.keys())
        for nested_value in value.values():
            keys.extend(unsafe_metadata_keys(nested_value))
        return [key for key in keys if isinstance(key, str)]
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(unsafe_metadata_keys(item))
        return keys
    return []


class AnalyzeDetection(BaseModel):
    input_id: str
    input_index: int
    kind: str
    category: str
    type: str
    source: str
    rule_id: str | None = None
    detector_id: str | None = None
    severity: Literal["low", "medium", "high", "critical"]
    action: Literal["Allow", "Warn", "Mask", "Block"]
    placeholder: str | None = None
    confidence: int
    reason_code: str
    match_count: int


class AnalyzeInputResult(BaseModel):
    input_id: str
    input_index: int
    kind: Literal["text", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "file", "attachment_chip"]
    content_included: bool
    content_scanned: bool
    decision_basis: Literal["no_detection", "detection", "content_unavailable", "metadata_only"]
    content_unavailable_reason: str | None = None
    limit_exceeded: str | None = None


class ContentUnavailableInput(BaseModel):
    input_id: str
    input_index: int
    kind: Literal["text", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "file", "attachment_chip"]
    reason: str
    limit_exceeded: str | None = None


class BusinessContextMatch(BaseModel):
    input_id: str
    input_index: int
    kind: str
    source: str
    category: str
    reason_code: str
    match_count: int
    matched_keywords: list[str]
    evidence_counts: dict[str, int]


class AnalyzeResponse(BaseModel):
    event_id: uuid.UUID
    request_id: str
    action: Literal["Allow", "Warn", "Mask", "Block"]
    checked_at: datetime
    risk_score: int
    risk_level: Literal["low", "medium", "high", "critical"]
    user_message: str
    allow_original_send: bool
    requires_user_confirmation: bool
    detections: list[AnalyzeDetection]
    input_results: list[AnalyzeInputResult]
    content_unavailable_inputs: list[ContentUnavailableInput]
    business_context_matches: list[BusinessContextMatch]
    client_request_id: str
    filter_config_revision: str
    masked_prompt: str | None = None


def risk_level_for_score(score: int) -> Literal["low", "medium", "high", "critical"]:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def response_detections(matched_inputs: list[tuple[int, AnalyzeInput, list[RuleMatch]]]) -> list[AnalyzeDetection]:
    detections: list[AnalyzeDetection] = []
    for input_index, input_item, matches in matched_inputs:
        for match in matches:
            detections.append(
                AnalyzeDetection(
                    input_id=input_item.input_id,
                    input_index=input_index,
                    kind=input_item.kind,
                    category=match.category,
                    type=match.type,
                    source=input_item.source,
                    rule_id=match.rule_id,
                    detector_id=match.detector_id,
                    severity=match.severity,
                    action=public_action(match.action),
                    placeholder=match.type,
                    confidence=match.confidence,
                    reason_code=match.reason_code,
                    match_count=match.match_count,
                )
            )
    return detections


def business_context_matches(matched_inputs: list[tuple[int, AnalyzeInput, list[RuleMatch]]]) -> list[BusinessContextMatch]:
    context_matches: list[BusinessContextMatch] = []
    for input_index, input_item, matches in matched_inputs:
        for match in matches:
            if match.source != "custom_context_rule":
                continue
            matched_keywords = match.safe_evidence.get("matched_keywords", [])
            if not isinstance(matched_keywords, list):
                matched_keywords = []
            context_matches.append(
                BusinessContextMatch(
                    input_id=input_item.input_id,
                    input_index=input_index,
                    kind=input_item.kind,
                    source=input_item.source,
                    category=match.category,
                    reason_code=match.reason_code,
                    match_count=match.match_count,
                    matched_keywords=[item for item in matched_keywords if isinstance(item, str)],
                    evidence_counts={"matched_condition_count": match.match_count},
                )
            )
    return context_matches


def event_input_rows(event_id: uuid.UUID, input_results: list[AnalyzeInputResult], payload: AnalyzeRequest) -> list[EventInput]:
    inputs_by_index = {index: item for index, item in enumerate(payload.inputs)}
    rows: list[EventInput] = []
    for result in input_results:
        input_item = inputs_by_index[result.input_index]
        rows.append(
            EventInput(
                id=uuid.uuid4(),
                event_id=event_id,
                input_id=result.input_id,
                input_index=result.input_index,
                kind=result.kind,
                source=result.source,
                size_bytes=input_item.size_bytes,
                content_included=result.content_included,
                content_scanned=result.content_scanned,
                decision_basis=result.decision_basis,
                content_unavailable_reason=result.content_unavailable_reason,
                limit_exceeded=result.limit_exceeded,
            )
        )
    return rows


def matched_keywords_for_evidence(safe_evidence: dict[str, Any]) -> list[str]:
    matched_keywords = safe_evidence.get("matched_keywords", [])
    if not isinstance(matched_keywords, list):
        return []
    return [item for item in matched_keywords if isinstance(item, str)]


def evidence_counts_for_match(match: RuleMatch) -> dict[str, Any]:
    counts: dict[str, Any] = {"match_count": match.match_count}
    if match.source == "custom_context_rule":
        counts["matched_condition_count"] = match.match_count
    return counts


def event_detection_rows(event_id: uuid.UUID, matched_inputs: list[tuple[int, AnalyzeInput, list[RuleMatch]]]) -> list[EventDetection]:
    rows: list[EventDetection] = []
    for input_index, input_item, matches in matched_inputs:
        for match in matches:
            rows.append(
                EventDetection(
                    id=uuid.uuid4(),
                    event_id=event_id,
                    input_id=input_item.input_id,
                    input_index=input_index,
                    kind=input_item.kind,
                    input_source=input_item.source,
                    filter_rule_id=match.rule_id,
                    detector_id=match.detector_id,
                    action=match.action,
                    placeholder=match.type,
                    category=match.category,
                    type=match.type,
                    source=match.source,
                    severity=match.severity,
                    confidence=match.confidence,
                    count=match.count,
                    reason_code=match.reason_code,
                    match_count=match.match_count,
                    safe_evidence=match.safe_evidence,
                    matched_keywords=matched_keywords_for_evidence(match.safe_evidence),
                    evidence_counts=evidence_counts_for_match(match),
                )
            )
    return rows


def user_message_for_action(action: str, has_unavailable_input: bool) -> str:
    if action == ACTION_BLOCK and has_unavailable_input:
        return "One or more inputs could not be scanned safely, so the send attempt was blocked."
    if action == ACTION_MASK:
        return "Sensitive data was detected and replaced with placeholders."
    if action == ACTION_WARN:
        return "Sensitive or governed content was detected. Review before sending."
    if action == ACTION_BLOCK:
        return "Sensitive or governed content was detected and should not be sent."
    return "No sensitive data was detected."


def public_action(action: str) -> Literal["Allow", "Warn", "Mask", "Block"]:
    return PUBLIC_ACTIONS.get(action, "Block")  # type: ignore[return-value]


def allow_original_send(action: str) -> bool:
    return action in {ACTION_ALLOW, ACTION_WARN}


def requires_user_confirmation(action: str, matches: list[RuleMatch]) -> bool:
    if action == ACTION_BLOCK:
        return False
    if action == ACTION_WARN:
        return True
    return action == ACTION_MASK and any(match.action == ACTION_WARN for match in matches)


def included_text_inputs(payload: AnalyzeRequest) -> list[tuple[int, AnalyzeInput]]:
    return [
        (index, item)
        for index, item in enumerate(payload.inputs)
        if item.kind == "text" and item.content_included and item.content is not None
    ]


def matched_text_inputs(text_inputs: list[tuple[int, AnalyzeInput]], rules: list[FilterRule]) -> list[tuple[int, AnalyzeInput, list[RuleMatch]]]:
    return [
        (index, item, matches)
        for index, item in text_inputs
        if (matches := evaluate_filter_rules(item.content or "", rules))
    ]


def joined_text_for_detection(text_inputs: list[tuple[int, AnalyzeInput]]) -> str:
    return "\n".join(item.content or "" for _index, item in text_inputs).strip()


def first_composer_input(text_inputs: list[tuple[int, AnalyzeInput]]) -> tuple[int, AnalyzeInput] | None:
    for index, item in text_inputs:
        if item.source == "composer":
            return index, item
    return None


def unavailable_inputs(payload: AnalyzeRequest) -> list[tuple[int, AnalyzeInput]]:
    return [(index, item) for index, item in enumerate(payload.inputs) if not item.content_included]


def content_unavailable_summaries(payload: AnalyzeRequest) -> list[ContentUnavailableInput]:
    summaries: list[ContentUnavailableInput] = []
    for index, item in unavailable_inputs(payload):
        reason = item.content_unavailable_reason
        if reason is None and item.kind == "attachment_metadata":
            reason = "metadata_only"
        if reason is None:
            reason = "unavailable"
        summaries.append(
            ContentUnavailableInput(
                input_id=item.input_id,
                input_index=index,
                kind=item.kind,
                source=item.source,
                reason=reason,
                limit_exceeded=item.limit_exceeded,
            )
        )
    return summaries


def input_results_for_payload(payload: AnalyzeRequest, detection_input_indexes: set[int]) -> list[AnalyzeInputResult]:
    results: list[AnalyzeInputResult] = []
    for index, item in enumerate(payload.inputs):
        if item.content_included:
            content_scanned = item.kind == "text"
            decision_basis = "detection" if index in detection_input_indexes else "no_detection"
        elif item.kind == "attachment_metadata":
            content_scanned = False
            decision_basis = "metadata_only"
        else:
            content_scanned = False
            decision_basis = "content_unavailable"

        results.append(
            AnalyzeInputResult(
                input_id=item.input_id,
                input_index=index,
                kind=item.kind,
                source=item.source,
                content_included=item.content_included,
                content_scanned=content_scanned,
                decision_basis=decision_basis,
                content_unavailable_reason=item.content_unavailable_reason,
                limit_exceeded=item.limit_exceeded,
            )
        )
    return results


def final_action_for_payload(action: str, payload: AnalyzeRequest) -> str:
    if unavailable_inputs(payload):
        return ACTION_BLOCK
    return action


def final_action_for_analyze_result(action: str, payload: AnalyzeRequest, matched_inputs: list[tuple[int, AnalyzeInput, list[RuleMatch]]]) -> str:
    action = final_action_for_payload(action, payload)
    has_non_composer_mask = any(
        item.source != "composer" and any(match.action == ACTION_MASK for match in item_matches)
        for _index, item, item_matches in matched_inputs
    )
    if action == ACTION_MASK and has_non_composer_mask:
        return ACTION_BLOCK
    return action


def score_for_final_action(score: int, action: str) -> int:
    if action == ACTION_BLOCK:
        return max(score, 95)
    return score


@router.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
async def analyze_prompt(
    payload: AnalyzeRequest,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyzeResponse:
    request_id = payload.client_request_id
    event_id = uuid.uuid4()
    checked_at = utc_now()
    rules = await load_active_filter_rules(session)
    text_inputs = included_text_inputs(payload)
    matched_inputs = matched_text_inputs(text_inputs, rules)
    matches = [match for _index, _item, item_matches in matched_inputs for match in item_matches]
    detection_text = joined_text_for_detection(text_inputs)
    detection_target = first_composer_input([(index, item) for index, item, item_matches in matched_inputs if item_matches])
    risk_score = score_for_matches(matches)
    action = action_for_matches(matches)
    has_unavailable_input = bool(unavailable_inputs(payload))
    action = final_action_for_analyze_result(action, payload, matched_inputs)
    risk_score = score_for_final_action(risk_score, action)
    risk_level = risk_level_for_score(risk_score)
    masking_matches = []
    if detection_target is not None:
        masking_matches = next(
            (item_matches for index, _item, item_matches in matched_inputs if index == detection_target[0]),
            [],
        )
    masking_detections = detections_for_masking(masking_matches)
    composer_text = detection_target[1].content if detection_target is not None else None
    masked = apply_placeholders(composer_text, masking_detections) if action == ACTION_MASK and masking_detections and composer_text else None
    active_filter_rule_set_version = payload.filter_config_revision or filter_rule_set_version(rules)
    hash_basis = detection_text or "|".join(f"{item.input_id}:{item.kind}:{item.source}:{item.size_bytes}" for item in payload.inputs)
    prompt_hash = compute_prompt_hash(workspace_id=str(current_user.id), prompt=hash_basis)
    detection_input_indexes = {index for index, _item, item_matches in matched_inputs if item_matches}
    input_results = input_results_for_payload(payload, detection_input_indexes)

    event = AnalysisEvent(
        id=event_id,
        user_id=current_user.id,
        login_id=current_user.login_id,
        client_request_id=payload.client_request_id,
        prompt_hash=prompt_hash.digest,
        prompt_hash_key_id=prompt_hash.key_id,
        action=action,
        risk_score=risk_score,
        risk_level=risk_level,
        filter_rule_set_version=active_filter_rule_set_version,
        filter_config_revision=payload.filter_config_revision,
        service=payload.context.ai_service,
        service_domain=payload.context.ai_service_domain,
        platform=payload.context.browser,
    )
    session.add(event)
    for row in event_input_rows(event_id, input_results, payload):
        session.add(row)
    for row in event_detection_rows(event_id, matched_inputs):
        session.add(row)

    current_user.last_event_at = checked_at
    await session.commit()

    return AnalyzeResponse(
        event_id=event_id,
        request_id=request_id,
        action=public_action(action),
        checked_at=checked_at,
        risk_score=risk_score,
        risk_level=risk_level,
        user_message=user_message_for_action(action, has_unavailable_input),
        allow_original_send=allow_original_send(action),
        requires_user_confirmation=requires_user_confirmation(action, matches),
        detections=response_detections(matched_inputs),
        input_results=input_results,
        content_unavailable_inputs=content_unavailable_summaries(payload),
        business_context_matches=business_context_matches(matched_inputs),
        client_request_id=payload.client_request_id,
        filter_config_revision=active_filter_rule_set_version,
        masked_prompt=masked.text if masked is not None else None,
    )
