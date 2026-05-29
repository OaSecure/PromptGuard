from fastapi import FastAPI

from app.routes.admin_users import router as admin_users_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.setup import router as setup_router
from app.routes.status import router as status_router


app = FastAPI(
    title="PromptGuard API",
    version="0.1.0",
    description="Self-hosted PromptGuard API.",
)

app.include_router(admin_users_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(status_router)
