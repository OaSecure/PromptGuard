from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.models.auth import User
from app.routes.auth import require_admin
from app.routes.health import build_health

router = APIRouter(prefix="/status", tags=["status"])


def dashboard_status_payload(health: dict[str, Any]) -> dict[str, Any]:
    dependencies = {item["name"]: item for item in health.get("dependencies", [])}
    return {
        "status": health["status"],
        "service": health["service"],
        "version": health["version"],
        "checked_at": health["checked_at"],
        "api": {
            "status": health["status"],
        },
        "postgres": dependencies.get("postgres", {"status": "unknown"}),
        "migrations": dependencies.get("migrations", {"status": "unknown"}),
    }


@router.get("/server")
async def server_status(
    response: Response,
    _admin_user: User = Depends(require_admin),
) -> dict[str, Any]:
    health = await build_health(include_optional=True)
    if health["status"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return dashboard_status_payload(health)
