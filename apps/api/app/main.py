from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routes.admin_users import router as admin_users_router
from app.routes.analyze import router as analyze_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.setup import router as setup_router
from app.routes.status import router as status_router

settings = get_settings()

app = FastAPI(
    title="PromptGuard API",
    version="0.1.0",
    description="Self-hosted PromptGuard API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(RequestValidationError)
async def safe_validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        safe_error = {key: value for key, value in error.items() if key != "input"}
        if "ctx" in safe_error:
            safe_error["ctx"] = {
                key: str(value) if isinstance(value, Exception) else value
                for key, value in safe_error["ctx"].items()
            }
        errors.append(safe_error)
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(admin_users_router)
app.include_router(analyze_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(status_router)
