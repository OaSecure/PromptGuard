import uuid
from datetime import datetime
from email.utils import parseaddr
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

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

UserRole = Literal["ADMIN", "USER"]
UserStatus = Literal["ACTIVE", "DISABLED"]


class AdminUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    role: UserRole = "USER"
    login_id: str | None = Field(default=None, min_length=2, max_length=80)
    username: str | None = Field(default=None, min_length=2, max_length=80)

    @field_validator("email", "login_id", "username", "display_name", "department")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("email")
    @classmethod
    def normalize_email_input(cls, value: str) -> str:
        stripped = value.strip()
        _, parsed = parseaddr(stripped)
        if parsed != stripped:
            raise ValueError("email must be a valid address")
        local_part, separator, domain = stripped.partition("@")
        domain_parts = domain.split(".")
        if (
            separator != "@"
            or not local_part
            or not domain
            or any(character.isspace() for character in stripped)
            or len(domain_parts) < 2
            or any(not part for part in domain_parts)
        ):
            raise ValueError("email must be a valid address")
        return stripped


class AdminRolePatchRequest(BaseModel):
    role: UserRole


class AdminStatusPatchRequest(BaseModel):
    status: UserStatus


class AdminUserResponse(BaseModel):
    user_id: uuid.UUID
    id: uuid.UUID
    login_id: str
    username: str
    email: str | None
    department: str | None
    display_name: str | None
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


def _safe_user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        user_id=user.id,
        id=user.id,
        login_id=user.login_id,
        username=user.username,
        email=user.email,
        department=user.department,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        created_at=getattr(user, "created_at", None),
        updated_at=getattr(user, "updated_at", None),
        last_login_at=user.last_login_at,
        last_event_at=user.last_event_at,
    )


async def _find_user_by_login_or_email(
    session: AsyncSession,
    *,
    login_id_normalized: str,
    email_normalized: str,
) -> User | None:
    result = await session.execute(
        select(User).where(
            (User.login_id_normalized == login_id_normalized) | (User.email_normalized == email_normalized)
        )
    )
    return result.scalar_one_or_none()


async def _get_target_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreateRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    del current_admin

    login_id = payload.login_id or payload.email
    username = payload.username or payload.display_name or login_id
    login_id_normalized = _normalize_identifier(login_id)
    email_normalized = _normalize_identifier(payload.email)

    if await _find_user_by_login_or_email(
        session,
        login_id_normalized=login_id_normalized,
        email_normalized=email_normalized,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user already exists")

    user = User(
        login_id=login_id,
        login_id_normalized=login_id_normalized,
        username=username,
        email=payload.email,
        email_normalized=email_normalized,
        department=payload.department,
        display_name=payload.display_name,
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


@router.get("", response_model=list[AdminUserResponse])
async def list_admin_users(
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[AdminUserResponse]:
    del current_admin

    result = await session.execute(select(User).order_by(User.created_at.desc(), User.login_id.asc()))
    return [_safe_user_response(user) for user in result.scalars().all()]


@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_admin_user(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    del current_admin

    return _safe_user_response(await _get_target_user(session, user_id))


@router.patch("/{user_id}/role", response_model=AdminUserResponse)
async def update_admin_user_role(
    user_id: uuid.UUID,
    payload: AdminRolePatchRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    user = await _get_target_user(session, user_id)
    if user.id == current_admin.id and payload.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin cannot demote self")
    user.role = payload.role
    await session.commit()
    await session.refresh(user)
    return _safe_user_response(user)


@router.patch("/{user_id}/status", response_model=AdminUserResponse)
async def update_admin_user_status(
    user_id: uuid.UUID,
    payload: AdminStatusPatchRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    user = await _get_target_user(session, user_id)
    if user.id == current_admin.id and payload.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin cannot disable self")
    user.status = payload.status
    await session.commit()
    await session.refresh(user)
    return _safe_user_response(user)
