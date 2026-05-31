from datetime import timedelta

from sqlalchemy import inspect

from app.core.config import Settings
from app.core.tokens import utc_now
from app.models.auth import DashboardSession, RefreshToken, User


def test_user_schema_is_login_id_centered_and_email_optional() -> None:
    user_columns = User.__table__.c
    assert {"login_id", "login_id_normalized", "username", "department", "role", "status", "password_hash"}.issubset(
        set(user_columns.keys())
    )
    assert user_columns.email.nullable is True
    assert user_columns.email_normalized.nullable is True
    assert "password" not in user_columns

    status_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in User.__table__.constraints
        if getattr(constraint, "sqltext", None) is not None
    }
    assert status_constraints["ck_users_status"] == "status in ('ACTIVE', 'DISABLED')"


def test_refresh_token_schema_stores_hash_and_idle_metadata_only() -> None:
    columns = RefreshToken.__table__.c
    assert columns.login_id.nullable is True
    assert columns.idle_expires_at.nullable is True
    assert columns.token_hash.type.length >= 64

    index_columns = {index.name: tuple(index.columns.keys()) for index in RefreshToken.__table__.indexes}
    assert index_columns["ix_refresh_tokens_login_expires"] == ("login_id", "expires_at")
    assert {
        "refresh_token",
        "raw_refresh_token",
        "plain_token",
        "token_value",
    }.isdisjoint(set(columns.keys()))


def test_refresh_idle_timeout_uses_documented_env_name() -> None:
    settings = Settings(REFRESH_IDLE_TIMEOUT_DAYS=9)

    assert settings.refresh_idle_timeout_days == 9


def test_dashboard_session_schema_is_hash_only_and_login_id_based() -> None:
    columns = DashboardSession.__table__.c
    assert columns.user_id.nullable is True
    assert columns.login_id.nullable is False
    assert columns.session_hash.type.length >= 128
    assert {
        "session_id",
        "raw_session_id",
        "dashboard_session_id",
        "cookie_value",
        "plain_session",
    }.isdisjoint(set(columns.keys()))

    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in DashboardSession.__table__.constraints
        if constraint.name
    }
    index_columns = {index.name: tuple(index.columns.keys()) for index in DashboardSession.__table__.indexes}
    assert unique_constraints["uq_dashboard_sessions_session_hash"] == ("session_hash",)
    assert index_columns["ix_dashboard_sessions_login_expires"] == ("login_id", "expires_at")


def test_dashboard_session_can_be_created_without_user_id() -> None:
    session = DashboardSession(
        login_id="admin",
        user_id=None,
        session_hash="a" * 64,
        expires_at=utc_now() + timedelta(hours=1),
    )

    assert session.user_id is None
    assert session.login_id == "admin"
    assert session.session_hash == "a" * 64


def test_metadata_matches_database_table_contract() -> None:
    mapper = inspect(DashboardSession)

    assert mapper.local_table.name == "dashboard_sessions"
