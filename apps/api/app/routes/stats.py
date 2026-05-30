import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection
from app.routes.auth import require_admin

router = APIRouter(prefix="/stats", tags=["stats"])

ACTIONS = ("ALLOW", "WARN", "MASK", "BLOCK")
RISK_LEVELS = ("low", "medium", "high", "critical")


class UserStatsRow(BaseModel):
    user_id: uuid.UUID
    login_id: str
    username: str
    display_name: str | None
    department: str | None
    role: str
    status: str
    last_event_at: datetime | None
    event_count: int
    blocked_count: int
    masked_count: int
    warned_count: int
    allowed_count: int
    action_distribution: dict[str, int]
    detection_distribution: dict[str, int]
    top_detector_category: str | None


class UserStatsAccumulator:
    def __init__(self) -> None:
        self.events: list[AnalysisEvent] = []
        self.actions: Counter[str] = Counter()
        self.detection_types: Counter[str] = Counter()
        self.detection_categories: Counter[str] = Counter()


class DailyEventBucket(BaseModel):
    date: str
    event_count: int
    action_distribution: dict[str, int]
    risk_level_distribution: dict[str, int]


class EventStatsResponse(BaseModel):
    event_count: int
    active_user_count: int
    action_distribution: dict[str, int]
    risk_level_distribution: dict[str, int]
    detection_type_distribution: dict[str, int]
    detection_category_distribution: dict[str, int]
    daily_buckets: list[DailyEventBucket]


def action_distribution(actions: Counter[str]) -> dict[str, int]:
    return {action: actions[action] for action in ACTIONS if actions[action] > 0}


def risk_level_distribution(risk_levels: Counter[str]) -> dict[str, int]:
    return {risk_level: risk_levels[risk_level] for risk_level in RISK_LEVELS if risk_levels[risk_level] > 0}


def top_detector_category(categories: Counter[str]) -> str | None:
    if not categories:
        return None
    return sorted(categories.items(), key=lambda item: (-item[1], item[0]))[0][0]


def row_for_user(user: User, accumulator: UserStatsAccumulator) -> UserStatsRow:
    event_count = len(accumulator.events)
    last_event_at = max((event.created_at for event in accumulator.events), default=user.last_event_at)

    return UserStatsRow(
        user_id=user.id,
        login_id=user.login_id,
        username=user.username,
        display_name=user.display_name,
        department=user.department,
        role=user.role,
        status=user.status,
        last_event_at=last_event_at,
        event_count=event_count,
        blocked_count=accumulator.actions["BLOCK"],
        masked_count=accumulator.actions["MASK"],
        warned_count=accumulator.actions["WARN"],
        allowed_count=accumulator.actions["ALLOW"],
        action_distribution=action_distribution(accumulator.actions),
        detection_distribution=dict(sorted(accumulator.detection_types.items())),
        top_detector_category=top_detector_category(accumulator.detection_categories),
    )


def sort_stats_rows(rows: list[UserStatsRow]) -> list[UserStatsRow]:
    return sorted(
        rows,
        key=lambda row: (
            -row.event_count,
            -(row.last_event_at.timestamp() if row.last_event_at is not None else 0),
            row.username.casefold(),
        ),
    )


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def date_window(days: int, *, as_of: date | None = None) -> list[date]:
    end_date = as_of or utc_today()
    start_date = end_date - timedelta(days=days - 1)
    return [start_date + timedelta(days=offset) for offset in range(days)]


def event_date(event: AnalysisEvent) -> date:
    created_at = event.created_at
    if created_at.tzinfo is None:
        return created_at.date()
    return created_at.astimezone(timezone.utc).date()


def event_stats_response(
    *,
    events: list[AnalysisEvent],
    detections: list[EventDetection],
    days: int,
    as_of: date | None = None,
) -> EventStatsResponse:
    days_in_window = date_window(days, as_of=as_of)
    allowed_dates = set(days_in_window)
    events_in_window = [event for event in events if event_date(event) in allowed_dates]
    event_ids = {event.id for event in events_in_window}

    actions = Counter(event.action for event in events_in_window)
    risk_levels = Counter(event.risk_level for event in events_in_window)
    active_user_ids = {event.user_id for event in events_in_window}

    detection_types: Counter[str] = Counter()
    detection_categories: Counter[str] = Counter()
    for detection in detections:
        if detection.event_id not in event_ids:
            continue
        detection_types[detection.type] += detection.count
        detection_categories[detection.category] += detection.count

    events_by_date: dict[date, list[AnalysisEvent]] = defaultdict(list)
    for event in events_in_window:
        events_by_date[event_date(event)].append(event)

    daily_buckets = []
    for bucket_date in days_in_window:
        bucket_events = events_by_date.get(bucket_date, [])
        bucket_actions = Counter(event.action for event in bucket_events)
        bucket_risk_levels = Counter(event.risk_level for event in bucket_events)
        daily_buckets.append(
            DailyEventBucket(
                date=bucket_date.isoformat(),
                event_count=len(bucket_events),
                action_distribution=action_distribution(bucket_actions),
                risk_level_distribution=risk_level_distribution(bucket_risk_levels),
            )
        )

    return EventStatsResponse(
        event_count=len(events_in_window),
        active_user_count=len(active_user_ids),
        action_distribution=action_distribution(actions),
        risk_level_distribution=risk_level_distribution(risk_levels),
        detection_type_distribution=dict(sorted(detection_types.items())),
        detection_category_distribution=dict(sorted(detection_categories.items())),
        daily_buckets=daily_buckets,
    )


@router.get("/users", response_model=list[UserStatsRow])
async def user_stats(
    limit: int = Query(default=50, ge=1, le=100),
    include_disabled: bool = True,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserStatsRow]:
    del current_admin

    users_result = await session.execute(select(User))
    users = list(users_result.scalars().all())
    if not include_disabled:
        users = [user for user in users if user.status != "DISABLED"]

    user_ids = {user.id for user in users}
    accumulators: dict[uuid.UUID, UserStatsAccumulator] = {
        user.id: UserStatsAccumulator()
        for user in users
    }

    events_result = await session.execute(select(AnalysisEvent).where(AnalysisEvent.user_id.in_(user_ids)))
    events = list(events_result.scalars().all())
    event_user_ids: dict[uuid.UUID, uuid.UUID] = {}
    for event in events:
        accumulator = accumulators.get(event.user_id)
        if accumulator is None:
            continue
        accumulator.events.append(event)
        accumulator.actions[event.action] += 1
        event_user_ids[event.id] = event.user_id

    if event_user_ids:
        detections_result = await session.execute(select(EventDetection).where(EventDetection.event_id.in_(event_user_ids)))
        for detection in detections_result.scalars().all():
            user_id = event_user_ids.get(detection.event_id)
            if user_id is None:
                continue
            accumulator = accumulators[user_id]
            accumulator.detection_types[detection.type] += detection.count
            accumulator.detection_categories[detection.category] += detection.count

    rows = [row_for_user(user, accumulators[user.id]) for user in users]
    return sort_stats_rows(rows)[:limit]


@router.get("/events", response_model=EventStatsResponse)
async def event_stats(
    days: int = Query(default=30, ge=1, le=90),
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> EventStatsResponse:
    del current_admin

    as_of = utc_today()
    window_start = datetime.combine(date_window(days, as_of=as_of)[0], time.min, tzinfo=timezone.utc)
    events_result = await session.execute(select(AnalysisEvent).where(AnalysisEvent.created_at >= window_start))
    events = list(events_result.scalars().all())

    event_ids = {event.id for event in events}
    detections: list[EventDetection] = []
    if event_ids:
        detections_result = await session.execute(select(EventDetection).where(EventDetection.event_id.in_(event_ids)))
        detections = list(detections_result.scalars().all())

    return event_stats_response(events=events, detections=detections, days=days, as_of=as_of)
