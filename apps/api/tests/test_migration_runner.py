from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
import app.models  # noqa: F401
from app.db import seed
from app.db.base import Base
from app.models.filters import FilterRule


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


def test_seed_default_admin_password_matches_documented_development_default(monkeypatch) -> None:
    monkeypatch.delenv("PROMPTGUARD_INITIAL_ADMIN_PASSWORD", raising=False)

    assert Settings().initial_admin_password == "1234"


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
    assert admin.login_id == "admin"
    assert admin.login_id_normalized == "admin"
    assert admin.username == "admin"
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
        login_id="admin",
        login_id_normalized="admin",
        username="admin",
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


@pytest.mark.anyio
async def test_builtin_filter_rule_seed_is_idempotent() -> None:
    session = _FakeSession()

    created_count = await seed.ensure_builtin_filter_rules(session)

    assert created_count == 4
    assert session.flush_count == 1
    assert all(isinstance(item, FilterRule) for item in session.added)
    assert {item.origin for item in session.added} == {"built_in"}
    assert {item.kind for item in session.added} == {"detector"}
    assert {item.detector_key for item in session.added} == {"EMAIL", "PHONE", "RRN", "CARD"}
    assert all(item.editable_fields == {"severity": True, "action": True, "enabled": True} for item in session.added)
    assert all(item.config_json == {} for item in session.added)


@pytest.mark.anyio
async def test_builtin_filter_rule_seed_does_not_duplicate_existing_detector() -> None:
    existing = SimpleNamespace(origin="built_in", kind="detector", detector_key="EMAIL")
    session = _FakeSession(existing=existing)

    created_count = await seed.ensure_builtin_filter_rules(session)

    assert created_count == 0
    assert session.added == []
    assert session.flush_count == 0


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
    assert "filter_rule_versions" not in tables


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
