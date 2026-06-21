# -*- coding: utf-8 -*-
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.types.common import SizeBucket
from app.privacy.size_bucket import persistence_size_bucket


class _PersistenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SafeEvidenceProjection(_PersistenceModel):
    value_lengths: list[int] = Field(default_factory=list)
    matched_group_ids: list[str] = Field(default_factory=list)
    matched_pattern_ids: list[str] = Field(default_factory=list)
    matched_condition_count: int | None = None


class EventProjection(_PersistenceModel):
    id: uuid.UUID
    user_id: uuid.UUID
    login_id: str
    client_request_id: str
    action: Literal["ALLOW", "WARN", "MASK", "BLOCK"]
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high", "critical"]
    filter_config_revision: str
    service: str
    service_domain: str
    platform: str


class EventInputProjection(_PersistenceModel):
    id: uuid.UUID
    event_id: uuid.UUID
    input_id: str
    input_index: int = Field(ge=0)
    kind: Literal["text", "file_reference", "attachment_metadata", "unsupported_attachment"]
    source: str
    size_bucket: SizeBucket
    content_included: bool
    content_scanned: bool
    decision_basis: Literal["no_detection", "detection", "content_unavailable", "metadata_only"]
    content_unavailable_reason: str | None = None
    limit_exceeded: str | None = None


class EventDetectionProjection(_PersistenceModel):
    id: uuid.UUID
    event_id: uuid.UUID
    input_id: str
    input_index: int = Field(ge=0)
    kind: str
    input_source: str
    filter_rule_id: str | None = None
    detector_id: str | None = None
    action: str
    placeholder: str
    category: str
    type: str
    source: str
    severity: Literal["low", "medium", "high", "critical"]
    confidence: int = Field(ge=0, le=100)
    count: int = Field(ge=0)
    reason_code: str
    match_count: int = Field(ge=0)
    safe_evidence: SafeEvidenceProjection
    matched_keywords: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)


class IdempotencyProjection(_PersistenceModel):
    login_id: str
    client_request_id: str
    event_id: uuid.UUID
    expires_at: datetime


class EventWriteProjection(_PersistenceModel):
    event: EventProjection
    inputs: list[EventInputProjection]
    detections: list[EventDetectionProjection]
    idempotency: IdempotencyProjection


def serialize_event_write(
    *, event_id: uuid.UUID, user_id: uuid.UUID, login_id: str, payload: Any, action: str,
    risk_score: int, risk_level: str, input_results: list[Any], matched_inputs: list[tuple[int, Any, list[Any]]],
    idempotency_expires_at: datetime,
) -> EventWriteProjection:
    inputs_by_index = dict(enumerate(payload.inputs))
    input_rows = [
        EventInputProjection(
            id=uuid.uuid4(), event_id=event_id, input_id=result.input_id, input_index=result.input_index,
            kind=result.kind, source=result.source,
            size_bucket=persistence_size_bucket(inputs_by_index[result.input_index].size_bytes),
            content_included=result.content_included, content_scanned=result.content_scanned,
            decision_basis=result.decision_basis, content_unavailable_reason=result.content_unavailable_reason,
            limit_exceeded=result.limit_exceeded,
        )
        for result in input_results
    ]
    detection_rows: list[EventDetectionProjection] = []
    for input_index, input_item, matches in matched_inputs:
        for match in matches:
            safe = _safe_evidence(match.safe_evidence)
            detection_rows.append(EventDetectionProjection(
                id=uuid.uuid4(), event_id=event_id, input_id=input_item.input_id, input_index=input_index,
                kind=input_item.kind, input_source=input_item.source, filter_rule_id=match.rule_id,
                detector_id=match.detector_id, action=match.action, placeholder=match.type,
                category=match.category, type=match.type, source=match.source, severity=match.severity,
                confidence=match.confidence, count=match.count, reason_code=match.reason_code,
                match_count=match.match_count, safe_evidence=safe,
                matched_keywords=safe.matched_pattern_ids,
                evidence_counts={"match_count": match.match_count, **({"matched_condition_count": match.match_count} if match.source == "custom_context_rule" else {})},
            ))
    return EventWriteProjection(
        event=EventProjection(
            id=event_id, user_id=user_id, login_id=login_id, client_request_id=payload.client_request_id,
            action=action, risk_score=risk_score, risk_level=risk_level,
            filter_config_revision=payload.filter_config_revision, service=payload.context.ai_service,
            service_domain=payload.context.ai_service_domain, platform=payload.context.browser,
        ),
        inputs=input_rows,
        detections=detection_rows,
        idempotency=IdempotencyProjection(
            login_id=login_id, client_request_id=payload.client_request_id,
            event_id=event_id, expires_at=idempotency_expires_at,
        ),
    )


def _safe_evidence(value: Any) -> SafeEvidenceProjection:
    if not isinstance(value, dict):
        return SafeEvidenceProjection()
    return SafeEvidenceProjection(
        value_lengths=[item for item in value.get("value_lengths", []) if isinstance(item, int) and item >= 0],
        matched_group_ids=[item for item in value.get("matched_group_ids", []) if isinstance(item, str)],
        matched_pattern_ids=[item for item in value.get("matched_pattern_ids", []) if isinstance(item, str)],
        matched_condition_count=value.get("matched_condition_count") if isinstance(value.get("matched_condition_count"), int) else None,
    )
