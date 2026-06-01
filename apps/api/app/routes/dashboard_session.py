import hmac
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.password import verify_password
from app.core.tokens import (
    create_dashboard_csrf_token,
    create_dashboard_session_token,
    hash_dashboard_csrf_token,
    hash_dashboard_session_token,
    utc_now,
)
from app.db.session import get_db_session
from app.models.auth import DashboardSession, User

router = APIRouter(prefix="/dashboard/session", tags=["dashboard-session"])


class DashboardLoginRequest(BaseModel):
    login_id: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("login_id")
    @classmethod
    def normalize_login_id_input(cls, value: str) -> str:
        return value.strip()


class DashboardUserResponse(BaseModel):
    id: uuid.UUID
    login_id: str
    username: str
    department: str | None
    display_name: str | None
    role: str
    status: str


class DashboardCsrfResponse(BaseModel):
    csrf_token: str


class DashboardLoginResponse(BaseModel):
    ok: bool
    user: DashboardUserResponse
    csrf_token: str
    expires_at: datetime


class DashboardLogoutResponse(BaseModel):
    ok: bool


def invalid_dashboard_session() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid dashboard session")


def dashboard_forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _safe_user_response(user: User) -> DashboardUserResponse:
    return DashboardUserResponse(
        id=user.id,
        login_id=user.login_id,
        username=user.username,
        department=user.department,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
    )


async def _find_user_by_login_id(session: AsyncSession, login_id: str) -> User | None:
    result = await session.execute(select(User).where(User.login_id_normalized == login_id.casefold()))
    return result.scalar_one_or_none()


def _set_cookie(
    response: Response,
    *,
    key: str,
    value: str,
    settings: Settings,
    httponly: bool,
    max_age: int | None,
) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=httponly,
        secure=settings.dashboard_cookie_secure,
        samesite=settings.dashboard_cookie_samesite,
        max_age=max_age,
        path="/",
    )


def _clear_cookie(response: Response, *, key: str, settings: Settings) -> None:
    response.delete_cookie(
        key=key,
        path="/",
        secure=settings.dashboard_cookie_secure,
        samesite=settings.dashboard_cookie_samesite,
    )


def _require_login_csrf(
    *,
    header_token: str | None,
    cookie_token: str | None,
) -> str:
    if not header_token or not cookie_token:
        raise dashboard_forbidden("csrf token required")
    if not hmac.compare_digest(header_token, cookie_token):
        raise dashboard_forbidden("csrf token mismatch")
    return header_token


def _require_session_csrf(*, header_token: str | None, session_row: DashboardSession) -> None:
    if not header_token:
        raise dashboard_forbidden("csrf token required")
    if not hmac.compare_digest(hash_dashboard_csrf_token(header_token), session_row.csrf_hash):
        raise dashboard_forbidden("csrf token mismatch")


async def require_dashboard_admin_session(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    session_cookie = request.cookies.get(get_settings().dashboard_session_cookie_name)
    session_row, user = await _load_dashboard_session(session_cookie=session_cookie, session=session)
    session_row.last_seen_at = utc_now()
    await session.commit()
    return user


async def require_dashboard_admin_mutation(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    session_cookie = request.cookies.get(get_settings().dashboard_session_cookie_name)
    session_row, user = await _load_dashboard_session(session_cookie=session_cookie, session=session)
    _require_session_csrf(header_token=x_csrf_token, session_row=session_row)
    session_row.last_seen_at = utc_now()
    await session.commit()
    return user


async def _load_dashboard_session(
    *,
    session_cookie: str | None,
    session: AsyncSession,
) -> tuple[DashboardSession, User]:
    if not session_cookie:
        raise invalid_dashboard_session()

    session_hash = hash_dashboard_session_token(session_cookie)
    result = await session.execute(
        select(DashboardSession, User)
        .join(User, DashboardSession.user_id == User.id)
        .where(DashboardSession.session_hash == session_hash)
    )
    row = result.one_or_none()
    if row is None:
        raise invalid_dashboard_session()

    session_row, user = row
    now = utc_now()
    if session_row.revoked_at is not None or session_row.expires_at <= now:
        raise invalid_dashboard_session()
    if user.status != "ACTIVE":
        raise dashboard_forbidden("user is not active")
    if user.role != "ADMIN":
        raise dashboard_forbidden("admin access required")
    return session_row, user


@router.get("/csrf", response_model=DashboardCsrfResponse)
async def csrf(response: Response) -> DashboardCsrfResponse:
    settings = get_settings()
    csrf_token, _csrf_hash = create_dashboard_csrf_token()
    _set_cookie(
        response,
        key=settings.dashboard_csrf_cookie_name,
        value=csrf_token,
        settings=settings,
        httponly=False,
        max_age=settings.dashboard_session_expires_hours * 60 * 60,
    )
    return DashboardCsrfResponse(csrf_token=csrf_token)


@router.post("/login", response_model=DashboardLoginResponse)
async def login(
    payload: DashboardLoginRequest,
    request: Request,
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardLoginResponse:
    csrf_cookie = request.cookies.get(get_settings().dashboard_csrf_cookie_name)
    csrf_token = _require_login_csrf(header_token=x_csrf_token, cookie_token=csrf_cookie)
    user = await _find_user_by_login_id(session, payload.login_id)

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if user.status != "ACTIVE":
        raise dashboard_forbidden("user is not active")
    if user.role != "ADMIN":
        raise dashboard_forbidden("admin access required")

    raw_session_token, session_hash, expires_at = create_dashboard_session_token()
    session.add(
        DashboardSession(
            user_id=user.id,
            session_hash=session_hash,
            csrf_hash=hash_dashboard_csrf_token(csrf_token),
            expires_at=expires_at,
        )
    )
    user.last_login_at = utc_now()
    await session.commit()

    settings = get_settings()
    _set_cookie(
        response,
        key=settings.dashboard_session_cookie_name,
        value=raw_session_token,
        settings=settings,
        httponly=True,
        max_age=settings.dashboard_session_expires_hours * 60 * 60,
    )
    _set_cookie(
        response,
        key=settings.dashboard_csrf_cookie_name,
        value=csrf_token,
        settings=settings,
        httponly=False,
        max_age=settings.dashboard_session_expires_hours * 60 * 60,
    )

    return DashboardLoginResponse(
        ok=True,
        user=_safe_user_response(user),
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


@router.get("/me", response_model=DashboardUserResponse)
async def me(current_user: User = Depends(require_dashboard_admin_session)) -> DashboardUserResponse:
    return _safe_user_response(current_user)


@router.post("/logout", response_model=DashboardLogoutResponse)
async def logout(
    request: Request,
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardLogoutResponse:
    session_cookie = request.cookies.get(get_settings().dashboard_session_cookie_name)
    session_row, _user = await _load_dashboard_session(session_cookie=session_cookie, session=session)
    _require_session_csrf(header_token=x_csrf_token, session_row=session_row)
    session_row.revoked_at = utc_now()
    await session.commit()

    settings = get_settings()
    _clear_cookie(response, key=settings.dashboard_session_cookie_name, settings=settings)
    _clear_cookie(response, key=settings.dashboard_csrf_cookie_name, settings=settings)
    return DashboardLogoutResponse(ok=True)
