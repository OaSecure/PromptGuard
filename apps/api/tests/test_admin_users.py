import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.core.password import verify_password
from app.routes import admin_users


class _ScalarResult:
    def __init__(self, items):
        self.items = items

    def scalar_one_or_none(self):
        return self.items[0] if self.items else None

    def scalars(self):
        return self

    def all(self):
        return self.items


class _FakeSession:
    def __init__(self, users=None):
        self.users = list(users or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "WHERE" not in statement_text:
            return _ScalarResult(sorted(self.users, key=lambda user: (user.created_at, user.login_id), reverse=True))
        return _ScalarResult([])

    async def get(self, model, user_id):
        return next((user for user in self.users if user.id == user_id), None)

    def add(self, item):
        now = datetime.now(timezone.utc)
        if item.id is None:
            item.id = uuid.uuid4()
        item.created_at = now
        item.updated_at = now
        self.added.append(item)
        self.users.append(item)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, item):
        self.refreshed.append(item)


def _user(role: str = "ADMIN", status_value: str = "ACTIVE") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id=f"{role.lower()}-{uuid.uuid4().hex[:6]}",
        login_id_normalized="admin",
        username="admin",
        email="admin@example.com",
        email_normalized="admin@example.com",
        department="Security",
        display_name="PromptGuard Admin",
        role=role,
        status=status_value,
        password_hash="secret-hash",
        password_hash_algorithm="argon2id",
        password_hash_params=None,
        created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
        last_login_at=None,
        last_event_at=None,
    )


def _client(
    fake_session: _FakeSession,
    *,
    allow_admin: bool = True,
    current_admin: SimpleNamespace | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(admin_users.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if not allow_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return current_admin or _user(role="ADMIN")

    app.dependency_overrides[admin_users.get_db_session] = override_session
    app.dependency_overrides[admin_users.require_admin] = override_admin
    return TestClient(app)


def _assert_safe_user_payload(body):
    forbidden_keys = {"password", "password_hash", "password_hash_algorithm", "password_hash_params", "token"}

    assert forbidden_keys.isdisjoint(body)
    assert body["event_count"] == 0
    assert body["blocked_count"] == 0
    assert body["masked_count"] == 0
    assert body["warned_count"] == 0


def test_create_admin_user_is_admin_only() -> None:
    client = _client(_FakeSession(), allow_admin=False)

    response = client.post(
        "/admin/users",
        json={
            "email": "new-user@example.com",
            "password": "ConfiguredUserPassword!456",
            "display_name": "New User",
            "role": "USER",
        },
    )

    assert response.status_code == 403


def test_create_admin_user_hashes_password_and_returns_safe_metadata() -> None:
    fake_session = _FakeSession()
    client = _client(fake_session)

    response = client.post(
        "/admin/users",
        json={
            "email": "New-User@Example.com",
            "password": "ConfiguredUserPassword!456",
            "display_name": "New User",
            "department": "Security",
            "role": "ADMIN",
        },
    )

    body = response.json()
    created_user = fake_session.added[0]
    assert response.status_code == 201
    assert body["user_id"] == str(created_user.id)
    assert body["id"] == str(created_user.id)
    assert body["login_id"] == "New-User@Example.com"
    assert body["email"] == "New-User@Example.com"
    assert body["role"] == "ADMIN"
    assert body["status"] == "ACTIVE"
    assert created_user.login_id_normalized == "new-user@example.com"
    assert created_user.email_normalized == "new-user@example.com"
    assert verify_password("ConfiguredUserPassword!456", created_user.password_hash)
    assert created_user.password_hash != "ConfiguredUserPassword!456"
    _assert_safe_user_payload(body)


def test_create_admin_user_rejects_duplicate_identifier() -> None:
    existing = _user()

    class DuplicateSession(_FakeSession):
        async def execute(self, statement):
            self.statements.append(str(statement))
            return _ScalarResult([existing])

    client = _client(DuplicateSession([existing]))

    response = client.post(
        "/admin/users",
        json={"email": existing.email, "password": "ConfiguredUserPassword!456"},
    )

    assert response.status_code == 409


def test_create_admin_user_rejects_malformed_email() -> None:
    client = _client(_FakeSession())

    for email in ["foo@", "@example.com", "a@b", "bad address@example.com"]:
        response = client.post(
            "/admin/users",
            json={"email": email, "password": "ConfiguredUserPassword!456"},
        )

        assert response.status_code == 422


def test_list_and_detail_return_safe_metadata() -> None:
    user = _user(role="USER")
    fake_session = _FakeSession([user])
    client = _client(fake_session)

    list_response = client.get("/admin/users")
    detail_response = client.get(f"/admin/users/{user.id}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()[0]["user_id"] == str(user.id)
    assert detail_response.json()["user_id"] == str(user.id)
    assert list_response.json()[0]["id"] == str(user.id)
    assert detail_response.json()["id"] == str(user.id)
    _assert_safe_user_payload(list_response.json()[0])
    _assert_safe_user_payload(detail_response.json())


def test_get_admin_user_returns_404_for_missing_user() -> None:
    client = _client(_FakeSession())

    response = client.get(f"/admin/users/{uuid.uuid4()}")

    assert response.status_code == 404


def test_role_and_status_patch_validate_values_and_update_existing_user() -> None:
    user = _user(role="USER")
    fake_session = _FakeSession([user])
    client = _client(fake_session)

    role_response = client.patch(f"/admin/users/{user.id}/role", json={"role": "ADMIN"})
    status_response = client.patch(f"/admin/users/{user.id}/status", json={"status": "DISABLED"})
    invalid_role_response = client.patch(f"/admin/users/{user.id}/role", json={"role": "OWNER"})
    invalid_status_response = client.patch(f"/admin/users/{user.id}/status", json={"status": "PENDING"})

    assert role_response.status_code == 200
    assert role_response.json()["role"] == "ADMIN"
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "DISABLED"
    assert invalid_role_response.status_code == 422
    assert invalid_status_response.status_code == 422
    assert fake_session.commits == 2


def test_admin_cannot_demote_or_disable_self() -> None:
    current_admin = _user(role="ADMIN")
    fake_session = _FakeSession([current_admin])
    client = _client(fake_session, current_admin=current_admin)

    role_response = client.patch(f"/admin/users/{current_admin.id}/role", json={"role": "USER"})
    status_response = client.patch(f"/admin/users/{current_admin.id}/status", json={"status": "DISABLED"})

    assert role_response.status_code == 400
    assert status_response.status_code == 400
    assert current_admin.role == "ADMIN"
    assert current_admin.status == "ACTIVE"
    assert fake_session.commits == 0


def test_admin_users_router_uses_admin_guard() -> None:
    guarded_paths = {
        "/admin/users",
        "/admin/users/{user_id}",
        "/admin/users/{user_id}/role",
        "/admin/users/{user_id}/status",
    }

    for route in admin_users.router.routes:
        if getattr(route, "path", None) in guarded_paths:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            assert admin_users.require_admin in dependency_calls
