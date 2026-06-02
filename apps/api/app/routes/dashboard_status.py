from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.auth import User
from app.models.filters import FilterRule
from app.routes.auth import require_admin
from app.routes.health import build_health

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

StatusValue = Literal["healthy", "degraded", "unhealthy", "unknown"]


class DashboardStatusResponse(BaseModel):
    status: StatusValue
    last_checked: str
    api_status: StatusValue
    postgres_status: StatusValue
    migration_status: StatusValue
    filter_rules_status: StatusValue


def sanitize_status(value: object) -> StatusValue:
    if value in {"healthy", "degraded", "unhealthy"}:
        return value  # type: ignore[return-value]
    return "unknown"


def dependency_status(health: dict[str, object], name: str) -> StatusValue:
    dependencies = health.get("dependencies", [])
    if not isinstance(dependencies, list):
        return "unknown"

    for item in dependencies:
        if isinstance(item, dict) and item.get("name") == name:
            return sanitize_status(item.get("status"))
    return "unknown"


async def filter_rules_status(session: AsyncSession) -> StatusValue:
    try:
        await session.execute(select(FilterRule.id).limit(1))
        return "healthy"
    except Exception:
        return "unhealthy"


def safe_last_checked(value: object) -> str:
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            pass
    try:
        return datetime.now(UTC).isoformat()
    except Exception:
        return "unknown"


def sanitize_dashboard_status(health: dict[str, object], filter_status: StatusValue) -> DashboardStatusResponse:
    overall = sanitize_status(health.get("status"))
    return DashboardStatusResponse(
        status=overall,
        last_checked=safe_last_checked(health.get("checked_at")),
        api_status=overall,
        postgres_status=dependency_status(health, "postgres"),
        migration_status=dependency_status(health, "migrations"),
        filter_rules_status=filter_status,
    )


def should_return_unavailable(payload: DashboardStatusResponse) -> bool:
    return "unhealthy" in {
        payload.postgres_status,
        payload.migration_status,
        payload.filter_rules_status,
    }


@router.get("/status", response_model=DashboardStatusResponse)
async def dashboard_status(
    response: Response,
    _admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardStatusResponse:
    health = await build_health(include_optional=False)
    payload = sanitize_dashboard_status(health, await filter_rules_status(session))
    if should_return_unavailable(payload):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
