from pathlib import Path
from types import SimpleNamespace

import pytest

import app.models  # noqa: F401
from app.db import seed
from app.db.base import Base


class _FakeResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        return self.item


class _FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.flush_count = 0

    async def execute(self, _statement):
        return _FakeResult(self.existing)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.anyio
async def test_seed_creates_default_admin_without_plaintext_password(monkeypatch) -> None:
    initial_password = "SeedPassword123!DoNotStore"
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(initial_admin_password=initial_password))
    session = _FakeSession()

    created = await seed.ensure_default_admin(session)

    assert created is True
    assert session.flush_count == 1
    assert len(session.added) == 1

    admin = session.added[0]
    assert admin.login_id == "ADMIN"
    assert admin.login_id_normalized == "admin"
    assert admin.username == "ADMIN"
    assert admin.role == "ADMIN"
    assert admin.status == "ACTIVE"
    assert admin.email is None
    assert admin.email_normalized is None
    assert admin.password_hash
    assert admin.password_hash != initial_password
    assert initial_password not in admin.password_hash
    assert not hasattr(admin, "password")


@pytest.mark.anyio
async def test_seed_is_idempotent_and_does_not_reset_existing_admin_password(monkeypatch) -> None:
    existing = SimpleNamespace(
        login_id="ADMIN",
        login_id_normalized="admin",
        username="ADMIN",
        role="ADMIN",
        status="ACTIVE",
        password_hash="existing-hash",
    )
    monkeypatch.setattr(
        seed,
        "get_settings",
        lambda: SimpleNamespace(initial_admin_password="DifferentPassword123!"),
    )
    session = _FakeSession(existing=existing)

    created = await seed.ensure_default_admin(session)

    assert created is False
    assert session.added == []
    assert session.flush_count == 0
    assert existing.password_hash == "existing-hash"


def test_migration_readiness_metadata_contains_current_stack_tables() -> None:
    tables = set(Base.metadata.tables)
    required_tables = {
        "users",
        "refresh_tokens",
        "dashboard_sessions",
        "analysis_events",
        "event_inputs",
        "event_detections",
        "filter_rules",
    }

    assert required_tables.issubset(tables)
    if "filter_rule_versions" in tables:
        assert "filter_rule_versions" in Base.metadata.tables


def test_startup_script_does_not_echo_secret_values() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "start_api.sh"
    content = script.read_text(encoding="utf-8")

    assert "alembic upgrade head" in content
    assert "python -m app.db.seed" in content
    assert "exec uvicorn app.main:app" in content
    assert "DATABASE_URL" not in content
    assert "ACCESS_TOKEN_SECRET" not in content
    assert "REFRESH_TOKEN_SECRET" not in content
    assert "PROMPTGUARD_INITIAL_ADMIN_PASSWORD" not in content
