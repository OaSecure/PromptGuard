import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password, verify_password
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
    id: uuid.UUID
    login_id: str
    username: str
    email: str | None
    department: str | None
    display_name: str | None
    role: str
    status: str


class LogoutResponse(BaseModel):
    ok: bool


class ChangePasswordResponse(BaseModel):
    ok: bool


def invalid_credentials() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")


async def get_user_by_login_id(session: AsyncSession, login_id: str) -> User | None:
    result = await session.execute(select(User).where(User.login_id_normalized == login_id.casefold()))
    return result.scalar_one_or_none()


def is_login_allowed(user: User | None, plain_password: str) -> bool:
    return user is not None and user.status == "ACTIVE" and verify_password(plain_password, user.password_hash)


async def issue_token_pair(session: AsyncSession, user: User) -> TokenResponse:
    access_token, access_token_expires_at = create_access_token(user.id)
    refresh_token, refresh_token_hash, refresh_token_expires_at = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=refresh_token_expires_at,
        )
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise invalid_credentials()

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise invalid_credentials()

    user = await session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise invalid_credentials()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    async with session.begin():
        user = await get_user_by_login_id(session, payload.login_id)
        if not is_login_allowed(user, payload.password):
            raise invalid_credentials()

        user.last_login_at = utc_now()
        return await issue_token_pair(session, user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        login_id=current_user.login_id,
        username=current_user.username,
        email=current_user.email,
        department=current_user.department,
        display_name=current_user.display_name,
        role=current_user.role,
        status=current_user.status,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
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
        if refresh_token.revoked_at is not None or refresh_token.expires_at <= now or user.status != "ACTIVE":
            raise invalid_credentials()

        new_token_id = uuid.uuid4()
        access_token, access_token_expires_at = create_access_token(user.id)
        new_refresh_token, new_refresh_token_hash, new_refresh_token_expires_at = create_refresh_token()

        session.add(
            RefreshToken(
                id=new_token_id,
                user_id=user.id,
                token_hash=new_refresh_token_hash,
                expires_at=new_refresh_token_expires_at,
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
async def logout(payload: LogoutRequest, session: AsyncSession = Depends(get_db_session)) -> LogoutResponse:
    token_hash = hash_refresh_token(payload.refresh_token)

    async with session.begin():
        result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        refresh_token = result.scalar_one_or_none()
        if refresh_token is not None and refresh_token.revoked_at is None:
            refresh_token.revoked_at = utc_now()

    return LogoutResponse(ok=True)


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
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
