import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password, verify_password
from app.core.rate_limit import rate_limit_key, rate_limiter
from app.core.config import get_settings
from app.core.tokens import create_access_token, create_refresh_token, decode_access_token, hash_refresh_token, utc_now
from app.db.session import get_db_session
from app.models.auth import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("login_id")
    @classmethod
    def normalize_login_id_input(cls, value: str) -> str:
        return value.strip()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class UserResponse(BaseModel):
    login_id: str
    username: str
    department: str | None
    display_name: str | None
    role: str
    status: str
    last_login_at: datetime | None


class LogoutResponse(BaseModel):
    ok: bool


class ChangePasswordResponse(BaseModel):
    ok: bool


def invalid_credentials() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")


def enforce_auth_rate_limit(request: Request, scope: str) -> None:
    settings = get_settings()
    rate_limiter.check(
        rate_limit_key(request, scope),
        settings.auth_rate_limit_requests,
        settings.auth_rate_limit_window_seconds,
    )


async def get_user_by_login_id(session: AsyncSession, login_id: str) -> User | None:
    result = await session.execute(select(User).where(User.login_id_normalized == login_id.casefold()))
    return result.scalar_one_or_none()


def is_login_allowed(user: User | None, plain_password: str) -> bool:
    return user is not None and user.status == "ACTIVE" and verify_password(plain_password, user.password_hash)


def refresh_idle_expires_at(now: datetime | None = None) -> datetime:
    settings = get_settings()
    return (now or utc_now()) + timedelta(days=getattr(settings, "refresh_idle_timeout_days", 14))


async def issue_token_pair(session: AsyncSession, user: User) -> TokenResponse:
    access_token, access_token_expires_at = create_access_token(user.id)
    refresh_token, refresh_token_hash, refresh_token_expires_at = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            login_id=user.login_id,
            token_hash=refresh_token_hash,
            expires_at=refresh_token_expires_at,
            idle_expires_at=refresh_idle_expires_at(),
        )
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
    )


async def require_active_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise invalid_credentials()

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise invalid_credentials()

    user = await session.get(User, user_id)
    if user is None:
        raise invalid_credentials()
    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")
    return user


async def require_admin(current_user: User = Depends(require_active_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return current_user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    enforce_auth_rate_limit(request, "auth:login")
    async with session.begin():
        user = await get_user_by_login_id(session, payload.login_id)
        if not is_login_allowed(user, payload.password):
            raise invalid_credentials()

        user.last_login_at = utc_now()
        return await issue_token_pair(session, user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(require_active_user)) -> UserResponse:
    return UserResponse(
        login_id=current_user.login_id,
        username=current_user.username,
        department=current_user.department,
        display_name=current_user.display_name,
        role=current_user.role,
        status=current_user.status,
        last_login_at=current_user.last_login_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    enforce_auth_rate_limit(request, "auth:refresh")
    token_hash = hash_refresh_token(payload.refresh_token)

    async with session.begin():
        result = await session.execute(
            select(RefreshToken, User)
            .join(User, RefreshToken.user_id == User.id)
            .where(RefreshToken.token_hash == token_hash)
        )
        row = result.one_or_none()
        if row is None:
            raise invalid_credentials()

        refresh_token, user = row
        now = utc_now()
        if (
            refresh_token.revoked_at is not None
            or refresh_token.expires_at <= now
            or (refresh_token.idle_expires_at is not None and refresh_token.idle_expires_at <= now)
        ):
            raise invalid_credentials()
        if user.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")

        new_token_id = uuid.uuid4()
        access_token, access_token_expires_at = create_access_token(user.id)
        new_refresh_token, new_refresh_token_hash, new_refresh_token_expires_at = create_refresh_token()

        session.add(
            RefreshToken(
                id=new_token_id,
                user_id=user.id,
                login_id=user.login_id,
                token_hash=new_refresh_token_hash,
                expires_at=new_refresh_token_expires_at,
                idle_expires_at=refresh_idle_expires_at(now),
            )
        )
        await session.flush()

        refresh_token.revoked_at = now
        refresh_token.replaced_by_token_id = new_token_id

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=new_refresh_token_expires_at,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    payload: LogoutRequest,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    token_hash = hash_refresh_token(payload.refresh_token)

    async with session.begin():
        result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        refresh_token = result.scalar_one_or_none()
        if (
            refresh_token is not None
            and refresh_token.revoked_at is None
            and (refresh_token.user_id == current_user.id or refresh_token.login_id == current_user.login_id)
        ):
            refresh_token.revoked_at = utc_now()

    return LogoutResponse(ok=True)


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChangePasswordResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise invalid_credentials()

    user = await session.get(User, current_user.id)
    if user is None or user.status != "ACTIVE":
        raise invalid_credentials()

    if not verify_password(payload.current_password, user.password_hash):
        raise invalid_credentials()

    user.password_hash = hash_password(payload.new_password)
    user.password_hash_algorithm = "argon2id"
    user.password_hash_params = None

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = utc_now()
    for refresh_token in result.scalars():
        refresh_token.revoked_at = now

    await session.commit()

    return ChangePasswordResponse(ok=True)
