import uuid

import pytest

from app.core.password import verify_password
from app.db import seed
from app.models.auth import User


class FakeSession:
    def __init__(self, existing_admin: User | None = None) -> None:
        self.existing_admin = existing_admin
        self.added: list[User] = []

    async def scalar(self, _query):
        return self.existing_admin

    def add(self, item: User) -> None:
        self.added.append(item)


def build_existing_admin() -> User:
    return User(
        id=uuid.uuid4(),
        login_id="legacy-admin",
        login_id_normalized="legacy-admin",
        username="legacy-admin",
        email="legacy@example.com",
        email_normalized="legacy@example.com",
        department="security",
        display_name="Legacy Admin",
        role="ADMIN",
        status="DISABLED",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$legacy$legacy",
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )


def test_default_admin_seed_password_is_hash_only_and_verifiable() -> None:
    initial_password = "MyChosenAdminPassword!123"

    password_hash = seed.hash_password(initial_password)

    assert password_hash != initial_password
    assert initial_password not in password_hash
    assert verify_password(initial_password, password_hash)


def test_default_admin_seed_login_id_is_admin() -> None:
    assert seed.DEFAULT_ADMIN_LOGIN_ID == "admin"


def test_initial_admin_password_can_come_from_environment(monkeypatch) -> None:
    chosen_password = "ConfiguredAdminPassword!456"
    monkeypatch.setenv(seed.INITIAL_ADMIN_PASSWORD_ENV, chosen_password)

    assert seed.get_initial_admin_password() == chosen_password


def test_default_admin_seed_password_is_v1_mvp_default(monkeypatch) -> None:
    monkeypatch.delenv(seed.INITIAL_ADMIN_PASSWORD_ENV, raising=False)

    assert seed.get_initial_admin_password() == "1234"
    assert seed.DEFAULT_INITIAL_ADMIN_PASSWORD == "1234"


@pytest.mark.anyio
async def test_seed_default_admin_creates_canonical_admin_when_absent(monkeypatch) -> None:
    monkeypatch.delenv(seed.INITIAL_ADMIN_PASSWORD_ENV, raising=False)
    session = FakeSession()

    admin, created = await seed.ensure_default_admin(session)

    assert created is True
    assert session.added == [admin]
    assert admin.login_id == "admin"
    assert admin.login_id_normalized == "admin"
    assert admin.username == "admin"
    assert admin.role == "ADMIN"
    assert admin.status == "ACTIVE"
    assert verify_password("1234", admin.password_hash)


@pytest.mark.anyio
async def test_seed_default_admin_uses_env_override_only_for_new_seed(monkeypatch) -> None:
    chosen_password = "ConfiguredAdminPassword!456"
    monkeypatch.setenv(seed.INITIAL_ADMIN_PASSWORD_ENV, chosen_password)
    session = FakeSession()

    admin, created = await seed.ensure_default_admin(session)

    assert created is True
    assert verify_password(chosen_password, admin.password_hash)
    assert verify_password("1234", admin.password_hash) is False


@pytest.mark.anyio
async def test_default_admin_seed_is_idempotent_and_does_not_reset_password() -> None:
    existing_admin = build_existing_admin()
    original_password_hash = existing_admin.password_hash
    session = FakeSession(existing_admin=existing_admin)

    normalized_admin, created = await seed.ensure_default_admin(session, initial_password="ShouldNotBeUsed!789")

    assert created is False
    assert session.added == []
    assert normalized_admin is existing_admin
    assert normalized_admin.password_hash == original_password_hash
    assert normalized_admin.login_id == "admin"
    assert normalized_admin.login_id_normalized == "admin"
    assert normalized_admin.username == "admin"
    assert normalized_admin.role == "ADMIN"
    assert normalized_admin.status == "ACTIVE"
    assert normalized_admin.display_name == "Legacy Admin"
