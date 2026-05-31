import importlib.util
from pathlib import Path

from app.core.password import verify_password


def load_admin_seed_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260528_0003_v09_username_admin_seed.py"
    )
    spec = importlib.util.spec_from_file_location("admin_seed_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_admin_seed_password_is_hash_only_and_verifiable() -> None:
    migration = load_admin_seed_migration()
    initial_password = "MyChosenAdminPassword!123"

    password_hash = migration.hash_initial_admin_password(initial_password)

    assert password_hash != initial_password
    assert initial_password not in password_hash
    assert verify_password(initial_password, password_hash)


def test_default_admin_seed_login_id_starts_as_admin_before_contract_migration() -> None:
    migration = load_admin_seed_migration()

    assert migration.DEFAULT_ADMIN_LOGIN_ID == "admin"


def test_auth_user_contract_migration_normalizes_admin_login_id() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260601_0007_auth_user_schema_contract.py"
    )
    migration_text = migration_path.read_text(encoding="utf-8")

    assert "login_id = 'ADMIN'" in migration_text
    assert "login_id_normalized = 'admin'" in migration_text
    assert "username = 'ADMIN'" in migration_text
    assert "status = 'ACTIVE'" in migration_text


def test_initial_admin_password_can_come_from_environment(monkeypatch) -> None:
    migration = load_admin_seed_migration()
    chosen_password = "ConfiguredAdminPassword!456"

    monkeypatch.setenv(migration.INITIAL_ADMIN_PASSWORD_ENV, chosen_password)

    assert migration.get_initial_admin_password() == chosen_password
