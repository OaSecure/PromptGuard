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

StatusValue = Literal["healthy", "degraded", "unhealthy", "disabled", "unknown"]


class DashboardDependencyStatus(BaseModel):
    status: StatusValue


class DashboardStatusResponse(BaseModel):
    status: StatusValue
    last_checked: str
    api: DashboardDependencyStatus
    postgres: DashboardDependencyStatus
    migrations: DashboardDependencyStatus
    filter_rules: DashboardDependencyStatus


def sanitize_status(value: object) -> StatusValue:
    if value in {"healthy", "degraded", "unhealthy", "disabled"}:
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
        return "unknown"


def sanitize_dashboard_status(health: dict[str, object], filter_status: StatusValue) -> DashboardStatusResponse:
    overall = sanitize_status(health.get("status"))
    checked_at = health.get("checked_at")
    return DashboardStatusResponse(
        status=overall,
        last_checked=checked_at if isinstance(checked_at, str) else "",
        api=DashboardDependencyStatus(status=overall),
        postgres=DashboardDependencyStatus(status=dependency_status(health, "postgres")),
        migrations=DashboardDependencyStatus(status=dependency_status(health, "migrations")),
        filter_rules=DashboardDependencyStatus(status=filter_status),
    )


@router.get("/status", response_model=DashboardStatusResponse)
async def dashboard_status(
    response: Response,
    _admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardStatusResponse:
    health = await build_health(include_optional=False)
    if health["status"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return sanitize_dashboard_status(health, await filter_rules_status(session))
