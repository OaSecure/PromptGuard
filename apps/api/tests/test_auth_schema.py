from datetime import timedelta

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

import app.models.auth as auth_models
from app.core.tokens import utc_now
from app.models import __all__ as model_exports
from app.models.auth import DashboardSession, RefreshToken, User


def _column_names(table) -> set[str]:
    return {column.name for column in table.columns}


def _constraint_names(table, constraint_type) -> set[str]:
    return {constraint.name for constraint in table.constraints if isinstance(constraint, constraint_type)}


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes if isinstance(index, Index)}


def test_user_schema_matches_mvp_login_contract() -> None:
    columns = _column_names(User.__table__)

    for name in {
        "login_id",
        "login_id_normalized",
        "username",
        "department",
        "role",
        "status",
        "password_hash",
        "password_hash_algorithm",
        "password_hash_params",
        "created_at",
        "updated_at",
        "last_login_at",
        "last_event_at",
    }:
        assert name in columns

    assert User.__table__.c.email.nullable
    assert User.__table__.c.email_normalized.nullable
    assert "password" not in columns
    assert "uq_users_login_id_normalized" in _constraint_names(User.__table__, UniqueConstraint)

    status_checks = [
        constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_users_status"
    ]
    assert status_checks
    status_sql = str(status_checks[0].sqltext)
    assert "ACTIVE" in status_sql
    assert "DISABLED" in status_sql
    assert "PENDING" not in status_sql


def test_refresh_token_schema_stores_hash_metadata_only() -> None:
    columns = _column_names(RefreshToken.__table__)

    for name in {
        "user_id",
        "login_id",
        "token_hash",
        "expires_at",
        "idle_expires_at",
        "revoked_at",
        "replaced_by_token_id",
        "created_at",
    }:
        assert name in columns

    assert RefreshToken.__table__.c.login_id.nullable
    assert "uq_refresh_tokens_token_hash" in _constraint_names(RefreshToken.__table__, UniqueConstraint)
    assert "ix_refresh_tokens_login_expires" in _index_names(RefreshToken.__table__)
    for forbidden in {"refresh_token", "raw_refresh_token", "plain_token", "token_value"}:
        assert forbidden not in columns


def test_dashboard_session_schema_prepares_hash_only_session_metadata() -> None:
    columns = _column_names(DashboardSession.__table__)

    for name in {"user_id", "login_id", "session_hash", "expires_at", "revoked_at", "created_at", "last_seen_at"}:
        assert name in columns

    assert DashboardSession.__table__.c.user_id.nullable
    assert not DashboardSession.__table__.c.login_id.nullable
    assert "uq_dashboard_sessions_session_hash" in _constraint_names(DashboardSession.__table__, UniqueConstraint)
    assert "ix_dashboard_sessions_login_expires" in _index_names(DashboardSession.__table__)
    for forbidden in {"session_id", "raw_session_id", "dashboard_session_id", "cookie_value", "plain_session"}:
        assert forbidden not in columns


def test_dashboard_session_model_allows_login_id_without_user_id() -> None:
    session = DashboardSession(
        user_id=None,
        login_id="admin",
        session_hash="hash-value",
        csrf_hash="csrf-hash-value",
        expires_at=utc_now() + timedelta(hours=1),
    )

    assert session.user_id is None
    assert session.login_id == "admin"
    assert session.session_hash == "hash-value"


def test_invite_and_registration_models_are_removed_from_exports() -> None:
    assert not hasattr(auth_models, "Invite")
    assert not hasattr(auth_models, "RegistrationSettings")
    assert "Invite" not in model_exports
    assert "RegistrationSettings" not in model_exports
