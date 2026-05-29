from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
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

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(status_router)
