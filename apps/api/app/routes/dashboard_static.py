from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings

router = APIRouter()

_PAGE_MAP = {
    "": "status.html",
    "admin": "admin.html",
    "event-detail": "event-detail.html",
    "events": "events.html",
    "filters": "filters.html",
    "home": "index.html",
    "login": "login.html",
    "overview": "overview.html",
    "status-page": "status.html",
    "users": "users.html",
}


def dashboard_static_root() -> Path:
    configured = Path(get_settings().dashboard_static_dir)
    if configured.exists():
        return configured

    repo_dashboard = Path(__file__).resolve().parents[3] / "dashboard"
    if repo_dashboard.exists():
        return repo_dashboard

    return configured


def _safe_dashboard_file(page: str) -> Path:
    root = dashboard_static_root().resolve()
    relative = _PAGE_MAP.get(page.rstrip("/"))
    if relative is None:
        raise HTTPException(status_code=404, detail="Dashboard page not found")

    candidate = (root / relative).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Dashboard page not found")
    return candidate


@router.get("/dashboard", include_in_schema=False)
async def redirect_dashboard_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/", status_code=307)


@router.get("/dashboard/", include_in_schema=False)
@router.get("/dashboard/{page}", include_in_schema=False)
async def serve_dashboard_page(page: str = "") -> FileResponse:
    return FileResponse(_safe_dashboard_file(page), media_type="text/html")


def register_dashboard_static(app: FastAPI) -> None:
    root = dashboard_static_root()
    static_dir = root / "static"
    public_dir = root / "public"

    if static_dir.exists():
        app.mount("/dashboard/static", StaticFiles(directory=static_dir), name="dashboard-static")
    if public_dir.exists():
        app.mount("/dashboard/public", StaticFiles(directory=public_dir), name="dashboard-public")
    app.include_router(router)
