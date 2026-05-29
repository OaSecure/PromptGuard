from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password
from app.db.session import get_db_session
from app.models.auth import User

router = APIRouter(prefix="/setup", tags=["setup"])

BOOTSTRAP_LOCK_ID = 761_202_605_230_001


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class BootstrapRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        display_name = value.strip()
        return display_name or None


class BootstrapResponse(BaseModel):
    id: UUID
    username: str
    display_name: str | None
    role: str
    status: str


async def admin_exists(session: AsyncSession) -> bool:
    result = await session.execute(select(func.count()).select_from(User).where(User.role == "ADMIN"))
    return result.scalar_one() > 0


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(session: AsyncSession = Depends(get_db_session)) -> SetupStatusResponse:
    return SetupStatusResponse(needs_setup=not await admin_exists(session))


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(
    payload: BootstrapRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BootstrapResponse:
    async with session.begin():
        await session.execute(text("select pg_advisory_xact_lock(:lock_id)").bindparams(lock_id=BOOTSTRAP_LOCK_ID))

        if await admin_exists(session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="setup already completed",
            )

        user = User(
            login_id="ADMIN",
            login_id_normalized="admin",
            username="admin",
            email=None,
            email_normalized=None,
            department=None,
            display_name=payload.display_name,
            role="ADMIN",
            status="ACTIVE",
            password_hash=hash_password(payload.password),
            password_hash_algorithm="argon2id",
            password_hash_params=None,
        )
        session.add(user)
        await session.flush()

    return BootstrapResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
    )
