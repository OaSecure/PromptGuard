from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection
from app.routes.dashboard_session import require_dashboard_admin_session
from app.routes.stats import ACTIONS, RISK_LEVELS, date_window, event_date, utc_today

router = APIRouter(prefix="/dashboard", tags=["dashboard-overview"])


class OverviewPeriodEventCount(BaseModel):
    date: str
    event_count: int
    action_counts: dict[str, int]
    risk_level_counts: dict[str, int]


class OverviewRecentEventSummary(BaseModel):
    created_at: datetime
    service: str | None
    action: str
    risk_level: str
    risk_score: int
    detection_count: int


class DashboardOverviewResponse(BaseModel):
    total_events: int
    blocked_count: int
    masked_count: int
    warned_count: int
    allowed_count: int
    active_users: int
    risk_level_counts: dict[str, int]
    action_counts: dict[str, int]
    period_event_counts: list[OverviewPeriodEventCount]
    recent_events: list[OverviewRecentEventSummary]


def _counts_for(values: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
    return {key: values[key] for key in keys}


def dashboard_overview_response(
    *,
    events: list[AnalysisEvent],
    detections: list[EventDetection],
    days: int,
    as_of: date | None = None,
    recent_limit: int = 5,
) -> DashboardOverviewResponse:
    days_in_window = date_window(days, as_of=as_of)
    allowed_dates = set(days_in_window)
    events_in_window = [event for event in events if event_date(event) in allowed_dates]

    actions = Counter(event.action for event in events_in_window)
    risk_levels = Counter(event.risk_level for event in events_in_window)
    detection_counts = Counter()
    for detection in detections:
        detection_counts[detection.event_id] += detection.count

    events_by_date: dict[date, list[AnalysisEvent]] = defaultdict(list)
    for event in events_in_window:
        events_by_date[event_date(event)].append(event)

    period_event_counts = []
    for bucket_date in days_in_window:
        bucket_events = events_by_date.get(bucket_date, [])
        period_event_counts.append(
            OverviewPeriodEventCount(
                date=bucket_date.isoformat(),
                event_count=len(bucket_events),
                action_counts=_counts_for(Counter(event.action for event in bucket_events), ACTIONS),
                risk_level_counts=_counts_for(Counter(event.risk_level for event in bucket_events), RISK_LEVELS),
            )
        )

    recent_events = [
        OverviewRecentEventSummary(
            created_at=event.created_at,
            service=event.service,
            action=event.action,
            risk_level=event.risk_level,
            risk_score=event.risk_score,
            detection_count=detection_counts[event.id],
        )
        for event in sorted(events_in_window, key=lambda item: item.created_at, reverse=True)[:recent_limit]
    ]

    return DashboardOverviewResponse(
        total_events=len(events_in_window),
        blocked_count=actions["BLOCK"],
        masked_count=actions["MASK"],
        warned_count=actions["WARN"],
        allowed_count=actions["ALLOW"],
        active_users=len({event.user_id for event in events_in_window}),
        risk_level_counts=_counts_for(risk_levels, RISK_LEVELS),
        action_counts=_counts_for(actions, ACTIONS),
        period_event_counts=period_event_counts,
        recent_events=recent_events,
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
    events_result = await session.execute(select(AnalysisEvent).where(AnalysisEvent.created_at >= window_start))
    events = list(events_result.scalars().all())

    event_ids = {event.id for event in events}
    detections: list[EventDetection] = []
    if event_ids:
        detections_result = await session.execute(select(EventDetection).where(EventDetection.event_id.in_(event_ids)))
        detections = list(detections_result.scalars().all())

    return dashboard_overview_response(events=events, detections=detections, days=days, as_of=as_of)
