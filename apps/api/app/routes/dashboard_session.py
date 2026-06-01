from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dashboard_sessions import (
    DASHBOARD_CSRF_COOKIE,
    DASHBOARD_CSRF_HEADER,
    DASHBOARD_SESSION_COOKIE,
    create_csrf_token,
    create_dashboard_session_token,
    hash_dashboard_session_token,
    verify_csrf_token,
)
from app.core.config import get_settings
from app.core.password import verify_password
from app.core.tokens import utc_now
from app.db.session import get_db_session
from app.models.auth import DashboardSession, User
from app.routes.auth import enforce_auth_rate_limit, get_user_by_login_id, invalid_credentials

router = APIRouter(prefix="/dashboard/session", tags=["dashboard-session"])

COOKIE_SAMESITE = "lax"


class CsrfResponse(BaseModel):
    csrf_token: str


class DashboardLoginRequest(BaseModel):
    login_id: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("login_id")
    @classmethod
    def normalize_login_id_input(cls, value: str) -> str:
        return value.strip()


class DashboardUserResponse(BaseModel):
    login_id: str
    username: str
    department: str | None
    role: str
    status: str


class DashboardLogoutResponse(BaseModel):
    ok: bool


def _safe_user_response(user: User) -> DashboardUserResponse:
    return DashboardUserResponse(
        login_id=user.login_id,
        username=user.username,
        department=user.department,
        role=user.role,
        status=user.status,
    )


def _set_dashboard_session_cookie(response: Response, raw_session_token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utc_now()).total_seconds()))
    response.set_cookie(
        DASHBOARD_SESSION_COOKIE,
        raw_session_token,
        max_age=max_age,
        httponly=True,
        secure=get_settings().environment != "development",
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _clear_dashboard_session_cookie(response: Response) -> None:
    response.delete_cookie(DASHBOARD_SESSION_COOKIE, path="/")


def _set_csrf_cookie(response: Response, csrf_hash: str) -> None:
    response.set_cookie(
        DASHBOARD_CSRF_COOKIE,
        csrf_hash,
        httponly=True,
        secure=get_settings().environment != "development",
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _validate_csrf(csrf_header: str | None, csrf_cookie_hash: str | None) -> None:
    if not verify_csrf_token(csrf_header, csrf_cookie_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid csrf token")


async def _load_active_dashboard_session(
    raw_session_token: str | None,
    session: AsyncSession,
) -> tuple[DashboardSession, User]:
    if not raw_session_token:
        raise invalid_credentials()

    session_hash = hash_dashboard_session_token(raw_session_token)
    result = await session.execute(
        select(DashboardSession, User)
        .join(User, DashboardSession.user_id == User.id)
        .where(DashboardSession.session_hash == session_hash)
    )
    row = result.one_or_none()
    if row is None:
        raise invalid_credentials()

    dashboard_session, user = row
    now = utc_now()
    if dashboard_session.revoked_at is not None or dashboard_session.expires_at <= now:
        raise invalid_credentials()
    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    dashboard_session.last_seen_at = now
    return dashboard_session, user


async def require_dashboard_admin(
    raw_session_token: Annotated[str | None, Cookie(alias=DASHBOARD_SESSION_COOKIE)] = None,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    _dashboard_session, user = await _load_active_dashboard_session(raw_session_token, session)
    await session.commit()
    return user


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(response: Response) -> CsrfResponse:
    raw_csrf_token, csrf_hash = create_csrf_token()
    _set_csrf_cookie(response, csrf_hash)
    return CsrfResponse(csrf_token=raw_csrf_token)


@router.post("/login", response_model=DashboardUserResponse)
async def login(
    payload: DashboardLoginRequest,
    request: Request,
    response: Response,
    csrf_header: Annotated[str | None, Header(alias=DASHBOARD_CSRF_HEADER)] = None,
    csrf_cookie_hash: Annotated[str | None, Cookie(alias=DASHBOARD_CSRF_COOKIE)] = None,
    session: AsyncSession = Depends(get_db_session),
) -> DashboardUserResponse:
    enforce_auth_rate_limit(request, "dashboard-session:login")
    _validate_csrf(csrf_header, csrf_cookie_hash)

    async with session.begin():
        user = await get_user_by_login_id(session, payload.login_id)
        if user is None or user.status != "ACTIVE" or not verify_password(payload.password, user.password_hash):
            raise invalid_credentials()
        if user.role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

        raw_session_token, session_hash, expires_at = create_dashboard_session_token()
        dashboard_session = DashboardSession(user_id=user.id, session_hash=session_hash, expires_at=expires_at)
        session.add(dashboard_session)
        user.last_login_at = utc_now()

    _set_dashboard_session_cookie(response, raw_session_token, expires_at)
    return _safe_user_response(user)


@router.get("/me", response_model=DashboardUserResponse)
async def me(current_admin: User = Depends(require_dashboard_admin)) -> DashboardUserResponse:
    return _safe_user_response(current_admin)


@router.post("/logout", response_model=DashboardLogoutResponse)
async def logout(
    response: Response,
    csrf_header: Annotated[str | None, Header(alias=DASHBOARD_CSRF_HEADER)] = None,
    csrf_cookie_hash: Annotated[str | None, Cookie(alias=DASHBOARD_CSRF_COOKIE)] = None,
    raw_session_token: Annotated[str | None, Cookie(alias=DASHBOARD_SESSION_COOKIE)] = None,
    session: AsyncSession = Depends(get_db_session),
) -> DashboardLogoutResponse:
    _validate_csrf(csrf_header, csrf_cookie_hash)

    if raw_session_token:
        try:
            dashboard_session, _user = await _load_active_dashboard_session(raw_session_token, session)
            dashboard_session.revoked_at = utc_now()
            await session.commit()
        except HTTPException as exc:
            if exc.status_code != status.HTTP_401_UNAUTHORIZED:
                raise

    _clear_dashboard_session_cookie(response)
    return DashboardLogoutResponse(ok=True)
