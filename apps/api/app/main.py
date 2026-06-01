from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routes.admin_users import router as admin_users_router
from app.routes.analyze import router as analyze_router
from app.routes.auth import router as auth_router
from app.routes.dashboard_filters import router as dashboard_filters_router
from app.routes.dashboard_session import router as dashboard_session_router
from app.routes.events import router as events_router
from app.routes.filters import router as filters_router
from app.routes.health import router as health_router
from app.routes.setup import router as setup_router
from app.routes.stats import router as stats_router
from app.routes.status import router as status_router

settings = get_settings()

app = FastAPI(
    title="PromptGuard API",
    version="0.1.0",
    description="Self-hosted PromptGuard API.",
)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    safe_errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

app.include_router(admin_users_router)
app.include_router(analyze_router)
app.include_router(auth_router)
app.include_router(dashboard_filters_router)
app.include_router(dashboard_session_router)
app.include_router(events_router)
app.include_router(filters_router)
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(stats_router)
app.include_router(status_router)
