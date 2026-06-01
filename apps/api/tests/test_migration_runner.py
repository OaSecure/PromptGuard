import asyncio
from pathlib import Path

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.db.base import Base
from app.db import seed
from app.models.auth import User
from app.models.events import AuditLog, EventDetection, EventInput, IdempotencyKey


API_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = API_ROOT / "scripts" / "start_api.sh"


class _FakeScalarResult:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _FakeSeedSession:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user
        self.added = []

    async def execute(self, statement):
        self.statement = statement
        return _FakeScalarResult(self.existing_user)

    def add(self, obj):
        self.added.append(obj)


def _column_names(table) -> set[str]:
    return {column.name for column in table.columns}


def _constraint_names(table, constraint_type) -> set[str]:
    return {constraint.name for constraint in table.constraints if isinstance(constraint, constraint_type)}


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes if isinstance(index, Index)}


def test_start_api_runner_runs_migration_seed_before_uvicorn() -> None:
    script = START_SCRIPT.read_text(encoding="utf-8")

    assert "python -m app.db.wait_for_db" in script
    assert "alembic upgrade head" in script
    assert "python -m app.db.seed" in script
    assert "exec uvicorn app.main:app" in script
    assert script.index("python -m app.db.wait_for_db") < script.index("alembic upgrade head")
    assert script.index("alembic upgrade head") < script.index("python -m app.db.seed")
    assert script.index("python -m app.db.seed") < script.index("exec uvicorn app.main:app")
    assert "DATABASE_URL" not in script
    assert "ACCESS_TOKEN_SECRET" not in script
    assert "REFRESH_TOKEN_SECRET" not in script


def test_default_admin_seed_creates_hash_only_admin(monkeypatch) -> None:
    monkeypatch.delenv(seed.INITIAL_ADMIN_PASSWORD_ENV, raising=False)
    fake_session = _FakeSeedSession()

    admin = asyncio.run(seed.ensure_default_admin(fake_session))

    assert fake_session.added == [admin]
    assert admin.login_id == "admin"
    assert admin.login_id_normalized == "admin"
    assert admin.username == "admin"
    assert admin.role == "ADMIN"
    assert admin.status == "ACTIVE"
    assert admin.password_hash
    assert admin.password_hash != seed.DEFAULT_ADMIN_PASSWORD
    assert seed.DEFAULT_ADMIN_PASSWORD not in admin.password_hash
    assert "password" not in _column_names(User.__table__)


def test_default_admin_seed_is_idempotent_and_does_not_reset_password() -> None:
    existing_hash = "existing-password-hash"
    existing = User(
        login_id="old-admin",
        login_id_normalized="old-admin",
        username="old-admin",
        email=None,
        email_normalized=None,
        role="USER",
        status="DISABLED",
        password_hash=existing_hash,
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )
    fake_session = _FakeSeedSession(existing_user=existing)

    admin = asyncio.run(seed.ensure_default_admin(fake_session))

    assert fake_session.added == []
    assert admin is existing
    assert admin.login_id == "admin"
    assert admin.login_id_normalized == "admin"
    assert admin.username == "admin"
    assert admin.role == "ADMIN"
    assert admin.status == "ACTIVE"
    assert admin.password_hash == existing_hash


def test_mvp_readiness_tables_are_present_in_metadata() -> None:
    for table_name in {
        "users",
        "refresh_tokens",
        "dashboard_sessions",
        "filter_rules",
        "idempotency_keys",
        "analysis_events",
        "event_inputs",
        "event_detections",
        "audit_logs",
    }:
        assert table_name in Base.metadata.tables


def test_event_input_schema_is_metadata_only() -> None:
    columns = _column_names(EventInput.__table__)

    for name in {
        "event_id",
        "input_id",
        "input_index",
        "kind",
        "source",
        "size_bytes",
        "content_included",
        "content_scanned",
        "decision_basis",
        "content_unavailable_reason",
        "limit_exceeded",
    }:
        assert name in columns

    for forbidden in {
        "content",
        "prompt",
        "prompt_text",
        "raw_prompt",
        "file_content",
        "masked_prompt",
        "original_filename",
        "raw_file_name",
        "raw_detected_value",
        "raw_match",
        "context_excerpt",
    }:
        assert forbidden not in columns


def test_event_detection_schema_has_safe_metadata_without_raw_value_columns() -> None:
    columns = _column_names(EventDetection.__table__)

    for name in {
        "event_id",
        "input_id",
        "input_index",
        "kind",
        "input_source",
        "category",
        "type",
        "filter_rule_id",
        "severity",
        "confidence",
        "action",
        "reason_code",
        "match_count",
        "matched_keywords",
        "evidence_counts",
        "safe_evidence",
    }:
        assert name in columns

    for forbidden in {
        "raw_detected_value",
        "raw_regex_match",
        "surrounding_context",
        "raw_span",
        "full_masked_prompt",
        "file_content",
    }:
        assert forbidden not in columns


def test_idempotency_and_audit_tables_are_minimal_metadata_only() -> None:
    idempotency_columns = _column_names(IdempotencyKey.__table__)
    audit_columns = _column_names(AuditLog.__table__)

    assert {"login_id", "client_request_id", "event_id", "created_at", "expires_at"} <= idempotency_columns
    assert "uq_idempotency_keys_login_request" in _constraint_names(IdempotencyKey.__table__, UniqueConstraint)
    assert "ix_idempotency_keys_expires_at" in _index_names(IdempotencyKey.__table__)

    assert {"actor_login_id", "action", "target_type", "target_id", "safe_metadata", "created_at"} <= audit_columns
    assert "ix_audit_logs_created_at" in _index_names(AuditLog.__table__)
    assert "ix_audit_logs_actor_created_at" in _index_names(AuditLog.__table__)
    for forbidden in {"request_body", "password", "token", "secret", "raw_payload"}:
        assert forbidden not in audit_columns


def test_event_detection_constraints_keep_safe_metadata_bounded() -> None:
    constraint_names = _constraint_names(EventDetection.__table__, CheckConstraint)

    assert "ck_event_detections_input_index_non_negative" in constraint_names
    assert "ck_event_detections_action" in constraint_names
    assert "ix_event_detections_event_input" in _index_names(EventDetection.__table__)
    assert "ix_event_detections_filter_rule_id" in _index_names(EventDetection.__table__)
