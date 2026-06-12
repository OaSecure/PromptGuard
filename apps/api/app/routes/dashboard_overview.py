import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection, EventInput
from app.routes.dashboard_session import require_dashboard_admin_session
from app.routes.stats import ACTIONS, RISK_LEVELS, date_window, event_date, utc_today

router = APIRouter(prefix="/dashboard", tags=["dashboard-overview"])


class OverviewActionCount(BaseModel):
    action: str
    count: int


class OverviewRiskLevelCount(BaseModel):
    risk_level: str
    count: int


class OverviewDetectorCategoryCount(BaseModel):
    category: str
    count: int


class OverviewPeriodBucket(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    event_count: int
    blocked_count: int
    masked_count: int
    warned_count: int


class DashboardOverviewResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    event_count: int
    blocked_count: int
    masked_count: int
    warned_count: int
    allowed_count: int
    active_user_count: int
    content_unavailable_event_count: int
    last_event_at: datetime | None
    action_counts: list[OverviewActionCount]
    risk_level_counts: list[OverviewRiskLevelCount]
    detector_category_counts: list[OverviewDetectorCategoryCount]
    period_buckets: list[OverviewPeriodBucket]


def _action_counts(values: Counter[str]) -> list[OverviewActionCount]:
    return [OverviewActionCount(action=action.lower(), count=values[action]) for action in ACTIONS]


def _risk_level_counts(values: Counter[str]) -> list[OverviewRiskLevelCount]:
    return [OverviewRiskLevelCount(risk_level=risk_level, count=values[risk_level]) for risk_level in RISK_LEVELS]


def _detector_category_counts(values: Counter[str]) -> list[OverviewDetectorCategoryCount]:
    return [
        OverviewDetectorCategoryCount(category=category, count=count)
        for category, count in sorted(values.items())
        if count > 0
    ]


def dashboard_overview_response(
    *,
    events: list[AnalysisEvent],
    login_ids_by_event_id: dict[uuid.UUID, str],
    detections: list[EventDetection],
    event_inputs: list[EventInput] | None = None,
    days: int,
    as_of: date | None = None,
) -> DashboardOverviewResponse:
    days_in_window = date_window(days, as_of=as_of)
    period_start = datetime.combine(days_in_window[0], time.min, tzinfo=timezone.utc)
    period_end = datetime.combine(days_in_window[-1], time.max, tzinfo=timezone.utc)
    allowed_dates = set(days_in_window)
    events_in_window = [event for event in events if event_date(event) in allowed_dates]
    event_ids = {event.id for event in events_in_window}

    actions = Counter(event.action for event in events_in_window)
    risk_levels = Counter(event.risk_level for event in events_in_window)
    detector_categories: Counter[str] = Counter()
    for detection in detections:
        if detection.event_id in event_ids:
            detector_categories[detection.category] += detection.count
    unavailable_event_ids = {
        event_input.event_id
        for event_input in event_inputs or []
        if event_input.event_id in event_ids and not event_input.content_included
    }

    events_by_date: dict[date, list[AnalysisEvent]] = defaultdict(list)
    for event in events_in_window:
        events_by_date[event_date(event)].append(event)

    period_buckets = []
    for bucket_date in days_in_window:
        bucket_events = events_by_date.get(bucket_date, [])
        bucket_actions = Counter(event.action for event in bucket_events)
        period_buckets.append(
            OverviewPeriodBucket(
                bucket_start=datetime.combine(bucket_date, time.min, tzinfo=timezone.utc),
                bucket_end=datetime.combine(bucket_date, time.max, tzinfo=timezone.utc),
                event_count=len(bucket_events),
                blocked_count=bucket_actions["BLOCK"],
                masked_count=bucket_actions["MASK"],
                warned_count=bucket_actions["WARN"],
            )
        )

    return DashboardOverviewResponse(
        period_start=period_start,
        period_end=period_end,
        event_count=len(events_in_window),
        blocked_count=actions["BLOCK"],
        masked_count=actions["MASK"],
        warned_count=actions["WARN"],
        allowed_count=actions["ALLOW"],
        active_user_count=len(
            {
                login_ids_by_event_id[event.id]
                for event in events_in_window
                if event.id in login_ids_by_event_id
            }
        ),
        content_unavailable_event_count=len(unavailable_event_ids),
        last_event_at=max((event.created_at for event in events_in_window), default=None),
        action_counts=_action_counts(actions),
        risk_level_counts=_risk_level_counts(risk_levels),
        detector_category_counts=_detector_category_counts(detector_categories),
        period_buckets=period_buckets,
    )


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    days: int = Query(default=30, ge=1, le=90),
    current_admin: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardOverviewResponse:
    del current_admin

    as_of = utc_today()
    window_start = datetime.combine(date_window(days, as_of=as_of)[0], time.min, tzinfo=timezone.utc)
    events_result = await session.execute(
        select(AnalysisEvent, User.login_id)
        .join(User, AnalysisEvent.user_id == User.id)
        .where(AnalysisEvent.created_at >= window_start)
    )
    event_rows = list(events_result.all())
    events = [event for event, _login_id in event_rows]
    login_ids_by_event_id = {event.id: login_id for event, login_id in event_rows}

    event_ids = {event.id for event in events}
    detections: list[EventDetection] = []
    if event_ids:
        detections_result = await session.execute(select(EventDetection).where(EventDetection.event_id.in_(event_ids)))
        detections = list(detections_result.scalars().all())
        inputs_result = await session.execute(select(EventInput).where(EventInput.event_id.in_(event_ids)))
        event_inputs = list(inputs_result.scalars().all())
    else:
        event_inputs = []

    return dashboard_overview_response(
        events=events,
        login_ids_by_event_id=login_ids_by_event_id,
        detections=detections,
        event_inputs=event_inputs,
        days=days,
        as_of=as_of,
    )
