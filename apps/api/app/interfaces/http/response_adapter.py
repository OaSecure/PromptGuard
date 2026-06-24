# -*- coding: utf-8 -*-
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

_PUBLIC_ACTIONS = {"ALLOW": "Allow", "WARN": "Warn", "MASK": "Mask", "BLOCK": "Block"}


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
    kind: Literal["text", "file_reference", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "attached_file", "pasted_file", "pasted_image", "screenshot_image", "attachment_chip"]
    content_included: bool
    content_scanned: bool
    decision_basis: Literal["no_detection", "detection", "content_unavailable", "metadata_only"]
    content_unavailable_reason: str | None = None
    limit_exceeded: str | None = None


class ContentUnavailableInput(BaseModel):
    input_id: str
    input_index: int
    kind: Literal["text", "file_reference", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "attached_file", "pasted_file", "pasted_image", "screenshot_image", "attachment_chip"]
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


def build_analyze_response(
    *, event_id: uuid.UUID, request_id: str, checked_at: datetime, action: str,
    risk_score: int, risk_level: str, payload: Any, matched_inputs: list[tuple[int, Any, list[Any]]],
    input_results: list[AnalyzeInputResult], masked_prompt: str | None, masked_source: str | None,
) -> AnalyzeResponse:
    has_unavailable = any(not item.content_included for item in payload.inputs)
    matches = [match for _index, _item, item_matches in matched_inputs for match in item_matches]
    usable_mask = masked_prompt if action == "MASK" and masked_source in {"composer", "converted_paste"} else None
    return AnalyzeResponse(
        event_id=event_id,
        request_id=request_id,
        action=_public_action(action),
        checked_at=checked_at,
        risk_score=risk_score,
        risk_level=risk_level,
        user_message=_user_message(action, has_unavailable),
        allow_original_send=action in {"ALLOW", "WARN"},
        requires_user_confirmation=_requires_confirmation(action, matches),
        detections=_response_detections(matched_inputs),
        input_results=input_results,
        content_unavailable_inputs=_content_unavailable(payload),
        business_context_matches=_business_context_matches(matched_inputs),
        client_request_id=payload.client_request_id,
        filter_config_revision=payload.filter_config_revision,
        masked_prompt=usable_mask,
    )


def _public_action(action: str) -> Literal["Allow", "Warn", "Mask", "Block"]:
    return _PUBLIC_ACTIONS.get(action, "Block")  # type: ignore[return-value]


def _user_message(action: str, unavailable: bool) -> str:
    if action == "BLOCK" and unavailable:
        return "One or more inputs could not be scanned safely, so the send attempt was blocked."
    return {
        "MASK": "Sensitive data was detected and replaced with placeholders.",
        "WARN": "Sensitive or governed content was detected. Review before sending.",
        "BLOCK": "Sensitive or governed content was detected and should not be sent.",
    }.get(action, "No sensitive data was detected.")


def _requires_confirmation(action: str, matches: list[Any]) -> bool:
    if action == "BLOCK":
        return False
    if action in {"MASK", "WARN"}:
        return True
    return False


def _response_detections(matched_inputs: list[tuple[int, Any, list[Any]]]) -> list[AnalyzeDetection]:
    return [AnalyzeDetection(
        input_id=item.input_id, input_index=index, kind=item.kind, category=match.category,
        type=match.type, source=item.source, rule_id=match.rule_id, detector_id=match.detector_id,
        severity=match.severity, action=_public_action(match.action), placeholder=match.type,
        confidence=match.confidence, reason_code=match.reason_code, match_count=match.match_count,
    ) for index, item, matches in matched_inputs for match in matches]


def _content_unavailable(payload: Any) -> list[ContentUnavailableInput]:
    result = []
    for index, item in enumerate(payload.inputs):
        if item.content_included:
            continue
        reason = item.content_unavailable_reason or ("metadata_only" if item.kind == "attachment_metadata" else "unavailable")
        result.append(ContentUnavailableInput(input_id=item.input_id, input_index=index, kind=item.kind,
                                              source=item.source, reason=reason, limit_exceeded=item.limit_exceeded))
    return result


def _business_context_matches(matched_inputs: list[tuple[int, Any, list[Any]]]) -> list[BusinessContextMatch]:
    result = []
    for index, item, matches in matched_inputs:
        for match in matches:
            if match.source != "custom_context_rule":
                continue
            keywords = match.safe_evidence.get("matched_pattern_ids", match.safe_evidence.get("matched_keywords", []))
            result.append(BusinessContextMatch(
                input_id=item.input_id, input_index=index, kind=item.kind, source=item.source,
                category=match.category, reason_code=match.reason_code, match_count=match.match_count,
                matched_keywords=[value for value in keywords if isinstance(value, str)] if isinstance(keywords, list) else [],
                evidence_counts={"matched_condition_count": match.match_count},
            ))
    return result
