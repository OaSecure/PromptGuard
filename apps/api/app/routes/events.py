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
from app.models.events import AnalysisEvent, EventDetection
from app.routes.auth import require_admin

router = APIRouter(prefix="/events", tags=["events"])

ActionFilter = Literal["ALLOW", "WARN", "MASK", "BLOCK"]
RiskLevelFilter = Literal["low", "medium", "high", "critical"]


class EventUser(BaseModel):
    user_id: uuid.UUID
    login_id: str
    username: str
    display_name: str | None
    department: str | None


class EventDetectionSummary(BaseModel):
    category: str
    type: str
    count: int


class EventDetectionResponse(BaseModel):
    category: str
    type: str
    source: str
    severity: str
    confidence: int
    count: int
    reason_code: str
    match_count: int
    safe_evidence: dict[str, Any]


class EventListItem(BaseModel):
    event_id: uuid.UUID
    created_at: datetime
    user: EventUser
    service: str | None
    action: str
    risk_score: int
    risk_level: str
    detection_category: str | None
    detection_type: str | None
    detection_count: int
    detail_available: bool = True


class EventDetail(EventListItem):
    platform: str | None
    detection_summary: list[EventDetectionSummary]
    detections: list[EventDetectionResponse]
    prompt_hash_prefix: str


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


def safe_user(user: User) -> EventUser:
    return EventUser(
        user_id=user.id,
        login_id=user.login_id,
        username=user.username,
        display_name=user.display_name,
        department=user.department,
    )


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


def list_item(event: AnalysisEvent, user: User, detections: list[EventDetection]) -> EventListItem:
    summary = summarize_detections(detections)
    return EventListItem(
        event_id=event.id,
        created_at=event.created_at,
        user=safe_user(user),
        service=event.service,
        action=event.action,
        risk_score=event.risk_score,
        risk_level=event.risk_level,
        detection_category=detection_category_label(summary),
        detection_type=detection_type_label(summary),
        detection_count=sum(item.count for item in summary),
        detail_available=True,
    )


def detail_item(event: AnalysisEvent, user: User, detections: list[EventDetection]) -> EventDetail:
    base = list_item(event, user, detections)
    summary = summarize_detections(detections)
    return EventDetail(
        **base.model_dump(),
        platform=event.platform,
        detection_summary=summary,
        detections=[
            EventDetectionResponse(
                category=detection.category,
                type=detection.type,
                source=detection.source,
                severity=detection.severity,
                confidence=detection.confidence,
                count=detection.count,
                reason_code=detection.reason_code,
                match_count=detection.match_count,
                safe_evidence=detection.safe_evidence,
            )
            for detection in sorted(detections, key=lambda item: (item.category, item.type, item.reason_code))
        ],
        prompt_hash_prefix=event.prompt_hash[:12],
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


@router.get("", response_model=list[EventListItem])
async def list_events(
    action: ActionFilter | None = None,
    risk_level: RiskLevelFilter | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: User = Depends(require_admin),
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

    return [
        list_item(event, user, detections_by_event_id.get(event.id, []))
        for event, user in rows
    ]


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
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
    return detail_item(event, user, detections_by_event_id.get(event.id, []))
