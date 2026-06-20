from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

import app.models  # noqa: F401
from app.db.base import Base
from app.db import startup


def repo_api_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_compose_text() -> str:
    return (repo_api_root().parents[1] / "compose.yml").read_text(encoding="utf-8")


def load_env_example_text() -> str:
    return (repo_api_root().parents[1] / ".env.example").read_text(encoding="utf-8")


def load_start_api_script() -> str:
    return (repo_api_root() / "scripts" / "start_api.sh").read_text(encoding="utf-8")


def get_migration_head() -> str:
    alembic_config = Config(str(repo_api_root() / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(repo_api_root() / "alembic"))
    script = ScriptDirectory.from_config(alembic_config)
    return script.get_current_head()


def test_start_api_runner_waits_migrates_seeds_then_runs_uvicorn(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(startup, "wait_for_configured_database", lambda: order.append("wait_for_db"))
    monkeypatch.setattr(startup, "run_alembic_upgrade", lambda: order.append("alembic_upgrade"))
    monkeypatch.setattr(startup, "run_default_admin_seed", lambda: order.append("seed_default_admin"))
    monkeypatch.setattr(startup, "run_uvicorn", lambda: order.append("uvicorn"))

    startup.main()

    assert order == ["wait_for_db", "alembic_upgrade", "seed_default_admin", "uvicorn"]


def test_compose_uses_startup_runner_and_v1_admin_default() -> None:
    compose_text = load_compose_text()
    env_example_text = load_env_example_text()
    start_api_script = load_start_api_script()

    assert "PROMPTGUARD_INITIAL_ADMIN_PASSWORD: ${PROMPTGUARD_INITIAL_ADMIN_PASSWORD:-1234}" in compose_text
    assert "command: /bin/sh /app/scripts/start_api.sh" in compose_text
    assert "PROMPTGUARD_INITIAL_ADMIN_PASSWORD=1234" in env_example_text
    assert "python -m app.db.startup" in start_api_script
    assert "ACCESS_TOKEN_SECRET=" not in start_api_script
    assert "REFRESH_TOKEN_SECRET=" not in start_api_script
    assert "DATABASE_URL=" not in start_api_script


def test_wbs48_required_metadata_tables_exist() -> None:
    table_names = set(Base.metadata.tables)

    assert "dashboard_sessions" in table_names
    assert "event_inputs" in table_names
    assert "idempotency_keys" in table_names
    assert "audit_logs" in table_names
    assert get_migration_head() == "20260620_0011"


def test_audit_logs_schema_is_metadata_only_with_required_indexes() -> None:
    audit_logs = Base.metadata.tables["audit_logs"]
    actual_columns = set(audit_logs.columns.keys())

    assert {
        "actor_login_id",
        "action",
        "target_type",
        "target_id",
        "safe_metadata",
        "created_at",
    }.issubset(actual_columns)
    assert {
        "request_body",
        "raw_request_body",
        "raw_payload",
        "password",
        "password_hash",
        "access_token",
        "refresh_token",
        "session_token",
    }.isdisjoint(actual_columns)

    actual_indexes = {tuple(index.columns.keys()) for index in audit_logs.indexes}
    assert ("created_at",) in actual_indexes
    assert ("actor_login_id", "created_at") in actual_indexes


def test_contract_tests_do_not_depend_on_retired_pr76_combined_migration() -> None:
    migration_files = {path.name for path in (repo_api_root() / "alembic" / "versions").iterdir()}

    assert "20260601_0008_mvp_readiness_tables.py" not in migration_files
