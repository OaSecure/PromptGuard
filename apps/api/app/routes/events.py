import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection, EventInput
from app.routes.dashboard_session import require_dashboard_admin_session

router = APIRouter(prefix="/dashboard/events", tags=["dashboard-events"])

ActionFilter = Literal["ALLOW", "WARN", "MASK", "BLOCK"]
RiskLevelFilter = Literal["low", "medium", "high", "critical"]
ALLOWED_EVIDENCE_COUNT_KEYS = {
    "match_count",
    "matched_condition_count",
    "keyword_count",
}


class EventDetectionSummary(BaseModel):
    category: str
    type: str
    count: int


class EventDetectionResponse(BaseModel):
    category: str
    type: str
    input_id: str | None
    input_index: int | None
    kind: str | None
    source: str
    rule_id: str | None
    detector_id: str | None
    severity: str
    action: str | None
    placeholder: str | None
    reason_code: str
    match_count: int


class EventInputResponse(BaseModel):
    input_id: str
    input_index: int
    kind: str
    source: str
    content_included: bool
    content_scanned: bool
    decision_basis: str
    content_unavailable_reason: str | None
    limit_exceeded: str | None


class BusinessContextMatch(BaseModel):
    input_id: str | None
    input_index: int | None
    kind: str | None
    source: str | None
    category: str
    reason_code: str
    match_count: int
    matched_keywords: list[str]
    evidence_counts: dict[str, Any]


class ContextRiskEvidence(BaseModel):
    enabled: bool
    status: str
    candidate_count: int
    accepted_count: int
    labels: list[str]
    status_counts: dict[str, int]
    highest_score_bucket: str | None = None
    highest_confidence_bucket: str | None = None
    failure_code: str | None
    reason_code: str
    classifier_model_versions: list[str]
    verifier_model_versions: list[str]


class EventListItem(BaseModel):
    event_id: uuid.UUID
    created_at: datetime
    login_id: str
    username: str
    service: str | None
    platform: str | None
    action: str
    risk_score: int
    risk_level: str
    primary_detection_category: str | None
    primary_detection_type: str | None
    detection_count: int
    input_count: int
    content_unavailable_count: int
    detail_available: bool = True


class EventDetail(EventListItem):
    detection_summary: list[EventDetectionSummary]
    detections: list[EventDetectionResponse]
    input_results: list[EventInputResponse]
    content_unavailable_inputs: list[EventInputResponse]
    business_context_matches: list[BusinessContextMatch]
    context_risk_evidence: ContextRiskEvidence | None


def apply_event_filters(
    statement: Select[tuple[AnalysisEvent, User]],
    *,
    action: ActionFilter | None,
    risk_level: RiskLevelFilter | None,
    user_id: uuid.UUID | None,
) -> Select[tuple[AnalysisEvent, User]]:
    if action is not None:
        statement = statement.where(AnalysisEvent.action == action)
    if risk_level is not None:
        statement = statement.where(AnalysisEvent.risk_level == risk_level)
    if user_id is not None:
        statement = statement.where(AnalysisEvent.user_id == user_id)
    return statement
def summarize_detections(detections: list[EventDetection]) -> list[EventDetectionSummary]:
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for detection in detections:
        grouped[(detection.category, detection.type)] += detection.count

    return [
        EventDetectionSummary(category=category, type=detection_type, count=count)
        for (category, detection_type), count in sorted(grouped.items())
    ]


def detection_type_label(summary: list[EventDetectionSummary]) -> str | None:
    if not summary:
        return None
    if len(summary) == 1:
        return summary[0].type
    return "MULTIPLE"


def detection_category_label(summary: list[EventDetectionSummary]) -> str | None:
    categories = sorted({item.category for item in summary})
    if not categories:
        return None
    if len(categories) == 1:
        return categories[0]
    return "MULTIPLE"


def is_content_unavailable(event_input: EventInput) -> bool:
    return (
        not event_input.content_scanned
        or event_input.decision_basis == "content_unavailable"
        or event_input.content_unavailable_reason is not None
    )


def input_response(event_input: EventInput) -> EventInputResponse:
    return EventInputResponse(
        input_id=event_input.input_id,
        input_index=event_input.input_index,
        kind=event_input.kind,
        source=event_input.source,
        content_included=event_input.content_included,
        content_scanned=event_input.content_scanned,
        decision_basis=event_input.decision_basis,
        content_unavailable_reason=event_input.content_unavailable_reason,
        limit_exceeded=event_input.limit_exceeded,
    )


def safe_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:50]


def safe_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key in ALLOWED_EVIDENCE_COUNT_KEYS and isinstance(item, int)}


def safe_int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, int) and item >= 0
    }


def is_business_context_detection(detection: EventDetection) -> bool:
    return detection.source == "custom_context_rule"


def context_risk_response(value: Any) -> ContextRiskEvidence | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    candidate_count = value.get("candidate_count")
    accepted_count = value.get("accepted_count")
    reason_code = value.get("reason_code")
    return ContextRiskEvidence(
        enabled=value.get("enabled") is True,
        status=status if isinstance(status, str) else "candidate",
        candidate_count=candidate_count if isinstance(candidate_count, int) else 0,
        accepted_count=accepted_count if isinstance(accepted_count, int) else 0,
        labels=safe_keywords(value.get("labels")),
        status_counts=safe_int_map(value.get("status_counts")),
        highest_score_bucket=value.get("highest_score_bucket") if isinstance(value.get("highest_score_bucket"), str) else None,
        highest_confidence_bucket=value.get("highest_confidence_bucket") if isinstance(value.get("highest_confidence_bucket"), str) else None,
        failure_code=value.get("failure_code") if isinstance(value.get("failure_code"), str) else None,
        reason_code=reason_code if isinstance(reason_code, str) else "RISK_CONTEXT_LR_ONLY",
        classifier_model_versions=safe_keywords(value.get("classifier_model_versions")),
        verifier_model_versions=safe_keywords(value.get("verifier_model_versions")),
    )


def list_item(
    event: AnalysisEvent,
    user: User,
    detections: list[EventDetection],
    inputs: list[EventInput],
) -> EventListItem:
    summary = summarize_detections(detections)
    return EventListItem(
        event_id=event.id,
        created_at=event.created_at,
        login_id=user.login_id,
        username=user.display_name or user.username,
        service=event.service,
        platform=event.platform,
        action=event.action,
        risk_score=event.risk_score,
        risk_level=event.risk_level,
        primary_detection_category=detection_category_label(summary),
        primary_detection_type=detection_type_label(summary),
        detection_count=sum(item.count for item in summary),
        input_count=len(inputs),
        content_unavailable_count=sum(1 for item in inputs if is_content_unavailable(item)),
        detail_available=True,
    )


def detail_item(
    event: AnalysisEvent,
    user: User,
    detections: list[EventDetection],
    inputs: list[EventInput],
) -> EventDetail:
    base = list_item(event, user, detections, inputs)
    summary = summarize_detections(detections)
    input_results = [
        input_response(item)
        for item in sorted(inputs, key=lambda item: item.input_index)
    ]
    content_unavailable_inputs = [
        input_response(item)
        for item in sorted(inputs, key=lambda item: item.input_index)
        if is_content_unavailable(item)
    ]
    return EventDetail(
        **base.model_dump(),
        detection_summary=summary,
        detections=[
            EventDetectionResponse(
                category=detection.category,
                type=detection.type,
                input_id=detection.input_id,
                input_index=detection.input_index,
                kind=detection.kind,
                source=detection.input_source or "unknown",
                rule_id=detection.filter_rule_id,
                detector_id=detection.detector_id,
                severity=detection.severity,
                action=detection.action,
                placeholder=detection.placeholder,
                reason_code=detection.reason_code,
                match_count=detection.match_count,
            )
            for detection in sorted(detections, key=lambda item: (item.category, item.type, item.reason_code))
        ],
        input_results=input_results,
        content_unavailable_inputs=content_unavailable_inputs,
        business_context_matches=[
            BusinessContextMatch(
                input_id=detection.input_id,
                input_index=detection.input_index,
                kind=detection.kind,
                source=detection.input_source,
                category=detection.category,
                reason_code=detection.reason_code,
                match_count=detection.match_count,
                matched_keywords=safe_keywords(detection.matched_keywords),
                evidence_counts=safe_counts(detection.evidence_counts),
            )
            for detection in sorted(detections, key=lambda item: (item.category, item.type, item.reason_code))
            if is_business_context_detection(detection) and (detection.matched_keywords or detection.evidence_counts)
        ],
        context_risk_evidence=context_risk_response(event.context_risk_evidence),
    )


async def load_detections_by_event_id(
    session: AsyncSession,
    event_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[EventDetection]]:
    if not event_ids:
        return {}

    result = await session.execute(select(EventDetection).where(EventDetection.event_id.in_(event_ids)))
    grouped: dict[uuid.UUID, list[EventDetection]] = defaultdict(list)
    for detection in result.scalars().all():
        grouped[detection.event_id].append(detection)
    return grouped


async def load_inputs_by_event_id(
    session: AsyncSession,
    event_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[EventInput]]:
    if not event_ids:
        return {}

    result = await session.execute(
        select(EventInput)
        .where(EventInput.event_id.in_(event_ids))
        .order_by(EventInput.event_id, EventInput.input_index)
    )
    grouped: dict[uuid.UUID, list[EventInput]] = defaultdict(list)
    for event_input in result.scalars().all():
        grouped[event_input.event_id].append(event_input)
    return grouped


@router.get("", response_model=list[EventListItem])
async def list_events(
    action: ActionFilter | None = None,
    risk_level: RiskLevelFilter | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> list[EventListItem]:
    del current_admin

    statement = select(AnalysisEvent, User).join(User, AnalysisEvent.user_id == User.id)
    statement = apply_event_filters(statement, action=action, risk_level=risk_level, user_id=user_id)
    statement = statement.order_by(AnalysisEvent.created_at.desc()).limit(limit)

    result = await session.execute(statement)
    rows = result.all()
    event_ids = [event.id for event, _user in rows]
    detections_by_event_id = await load_detections_by_event_id(session, event_ids)
    inputs_by_event_id = await load_inputs_by_event_id(session, event_ids)

    return [
        list_item(event, user, detections_by_event_id.get(event.id, []), inputs_by_event_id.get(event.id, []))
        for event, user in rows
    ]


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: uuid.UUID,
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> EventDetail:
    del current_admin

    result = await session.execute(
        select(AnalysisEvent, User)
        .join(User, AnalysisEvent.user_id == User.id)
        .where(AnalysisEvent.id == event_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")

    event, user = row
    detections_by_event_id = await load_detections_by_event_id(session, [event.id])
    inputs_by_event_id = await load_inputs_by_event_id(session, [event.id])
    return detail_item(
        event,
        user,
        detections_by_event_id.get(event.id, []),
        inputs_by_event_id.get(event.id, []),
    )
