from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password
from app.db.session import get_db_session
from app.models.auth import User
from app.routes.auth import require_admin

router = APIRouter(prefix="/dashboard/users", tags=["dashboard-users"])

UserRole = Literal["ADMIN", "USER"]
UserStatus = Literal["ACTIVE", "DISABLED"]


class DashboardUserCreateRequest(BaseModel):
    login_id: str = Field(min_length=2, max_length=80)
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    department: str | None = Field(default=None, max_length=120)
    role: UserRole = "USER"

    @field_validator("login_id", "username", "department")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("login_id")
    @classmethod
    def login_id_must_be_safe(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("login_id must not contain whitespace")
        return value


class AdminRolePatchRequest(BaseModel):
    role: UserRole


class AdminStatusPatchRequest(BaseModel):
    status: UserStatus


class DashboardUserResponse(BaseModel):
    login_id: str
    username: str
    department: str | None
    role: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None
    last_event_at: datetime | None = None
    event_count: int = 0
    blocked_count: int = 0
    masked_count: int = 0
    warned_count: int = 0


def _normalize_identifier(value: str) -> str:
    return value.strip().casefold()


def _safe_user_response(user: User) -> DashboardUserResponse:
    return DashboardUserResponse(
        login_id=user.login_id,
        username=user.username,
        department=user.department,
        role=user.role,
        status=user.status,
        created_at=getattr(user, "created_at", None),
        updated_at=getattr(user, "updated_at", None),
        last_login_at=user.last_login_at,
        last_event_at=user.last_event_at,
    )


async def _find_user_by_login(
    session: AsyncSession,
    *,
    login_id_normalized: str,
) -> User | None:
    result = await session.execute(select(User).where(User.login_id_normalized == login_id_normalized))
    return result.scalar_one_or_none()


async def _get_target_user(session: AsyncSession, login_id: str) -> User:
    user = await _find_user_by_login(session, login_id_normalized=_normalize_identifier(login_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@router.post("", response_model=DashboardUserResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard_user(
    payload: DashboardUserCreateRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardUserResponse:
    del current_admin

    login_id_normalized = _normalize_identifier(payload.login_id)

    if await _find_user_by_login(session, login_id_normalized=login_id_normalized):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user already exists")

    user = User(
        login_id=payload.login_id,
        login_id_normalized=login_id_normalized,
        username=payload.username,
        email=None,
        email_normalized=None,
        department=payload.department,
        display_name=payload.username,
        role=payload.role,
        status="ACTIVE",
        password_hash=hash_password(payload.password),
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user already exists") from exc
    await session.refresh(user)
    return _safe_user_response(user)


@router.get("", response_model=list[DashboardUserResponse])
async def list_dashboard_users(
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[DashboardUserResponse]:
    del current_admin

    result = await session.execute(select(User).order_by(User.created_at.desc(), User.login_id.asc()))
    return [_safe_user_response(user) for user in result.scalars().all()]


@router.patch("/{login_id}/role", response_model=DashboardUserResponse)
async def update_dashboard_user_role(
    login_id: str,
    payload: AdminRolePatchRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardUserResponse:
    user = await _get_target_user(session, login_id)
    if user.id == current_admin.id and payload.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin cannot demote self")
    user.role = payload.role
    await session.commit()
    await session.refresh(user)
    return _safe_user_response(user)


@router.patch("/{login_id}/status", response_model=DashboardUserResponse)
async def update_dashboard_user_status(
    login_id: str,
    payload: AdminStatusPatchRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardUserResponse:
    user = await _get_target_user(session, login_id)
    if user.id == current_admin.id and payload.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin cannot disable self")
    user.status = payload.status
    await session.commit()
    await session.refresh(user)
    return _safe_user_response(user)
