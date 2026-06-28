import uuid
from datetime import datetime, timedelta, timezone
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
    def __init__(self, users=None, events=None):
        self.users = list(users or [])
        self.events = list(events or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "analysis_events" in statement_text:
            params = statement.compile().params
            cutoff = next((value for value in params.values() if isinstance(value, datetime)), None)
            if cutoff is None:
                return _ScalarResult(self.events)
            return _ScalarResult([event for event in self.events if event.created_at >= cutoff])
        if "users.role =" in statement_text and "users.status =" in statement_text:
            return _ScalarResult([user for user in self.users if user.role == "ADMIN" and user.status == "ACTIVE"])
        if "WHERE" in statement_text and "users.login_id_normalized" in statement_text:
            params = statement.compile().params
            login_id_normalized = next((value for key, value in params.items() if key.startswith("login_id_normalized")), None)
            return _ScalarResult(
                [user for user in self.users if login_id_normalized is None or user.login_id_normalized == login_id_normalized]
            )
        if "WHERE" not in statement_text:
            return _ScalarResult(sorted(self.users, key=lambda user: (user.created_at, user.login_id), reverse=True))
        return _ScalarResult(self.users[:1])

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


def _user(role: str = "ADMIN", status_value: str = "ACTIVE", login_id: str | None = None) -> SimpleNamespace:
    login_id = login_id or f"{role.lower()}-{uuid.uuid4().hex[:6]}"
    return SimpleNamespace(
        id=uuid.uuid4(),
        login_id=login_id,
        login_id_normalized=login_id.casefold(),
        username=login_id,
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


def _event(user: SimpleNamespace, action: str, created_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        action=action,
        created_at=created_at,
    )


def _json_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _client(
    fake_session: _FakeSession,
    *,
    allow_session: bool = True,
    allow_mutation: bool = True,
    current_admin: SimpleNamespace | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(admin_users.router)

    async def override_session():
        yield fake_session

    async def override_dashboard_session():
        if not allow_session:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return current_admin or _user(role="ADMIN")

    async def override_dashboard_mutation():
        if not allow_mutation:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token required")
        return current_admin or _user(role="ADMIN")

    app.dependency_overrides[admin_users.get_db_session] = override_session
    app.dependency_overrides[admin_users.require_dashboard_admin_session] = override_dashboard_session
    app.dependency_overrides[admin_users.require_dashboard_admin_mutation] = override_dashboard_mutation
    return TestClient(app)


def _assert_safe_user_payload(body):
    forbidden_keys = {
        "id",
        "user_id",
        "email",
        "updated_at",
        "password",
        "password_hash",
        "password_hash_algorithm",
        "password_hash_params",
        "token",
        "session",
        "session_id",
    }

    assert forbidden_keys.isdisjoint(body)
    assert body["event_count"] == 0
    assert body["blocked_count"] == 0
    assert body["masked_count"] == 0
    assert body["warned_count"] == 0


def _assert_no_sensitive_user_payload(body):
    forbidden_keys = {
        "id",
        "user_id",
        "email",
        "updated_at",
        "password",
        "password_hash",
        "password_hash_algorithm",
        "password_hash_params",
        "token",
        "session",
        "session_id",
    }
    assert forbidden_keys.isdisjoint(body)


def test_create_dashboard_user_is_admin_only() -> None:
    client = _client(_FakeSession(), allow_mutation=False)

    response = client.post(
        "/dashboard/users",
        json={
            "login_id": "new-user",
            "username": "New User",
            "password": "ConfiguredUserPassword!456",
            "role": "USER",
        },
    )

    assert response.status_code == 403


def test_dashboard_users_rejects_bearer_only_without_dashboard_session() -> None:
    app = FastAPI()
    app.include_router(admin_users.router)

    async def override_session():
        yield _FakeSession()

    app.dependency_overrides[admin_users.get_db_session] = override_session
    client = TestClient(app)

    response = client.get("/dashboard/users", headers={"Authorization": "Bearer extension-admin-token"})

    assert response.status_code == 401


def test_create_dashboard_user_hashes_password_and_returns_safe_metadata() -> None:
    fake_session = _FakeSession()
    client = _client(fake_session)

    response = client.post(
        "/dashboard/users",
        json={
            "login_id": "new-user",
            "username": "New User",
            "password": "ConfiguredUserPassword!456",
            "department": "Security",
            "role": "ADMIN",
        },
    )

    body = response.json()
    created_user = fake_session.added[0]
    assert response.status_code == 201
    assert body["login_id"] == "new-user"
    assert body["username"] == "New User"
    assert body["role"] == "ADMIN"
    assert body["status"] == "ACTIVE"
    assert created_user.login_id_normalized == "new-user"
    assert created_user.email is None
    assert created_user.email_normalized is None
    assert verify_password("ConfiguredUserPassword!456", created_user.password_hash)
    assert created_user.password_hash != "ConfiguredUserPassword!456"
    _assert_safe_user_payload(body)


def test_create_dashboard_user_rejects_duplicate_login_id() -> None:
    existing = _user()

    class DuplicateSession(_FakeSession):
        async def execute(self, statement):
            self.statements.append(str(statement))
            return _ScalarResult([existing])

    client = _client(DuplicateSession([existing]))

    response = client.post(
        "/dashboard/users",
        json={"login_id": existing.login_id, "username": "Duplicate", "password": "ConfiguredUserPassword!456"},
    )

    assert response.status_code == 409


def test_create_dashboard_user_rejects_missing_or_malformed_login_id() -> None:
    client = _client(_FakeSession())

    for payload in [
        {"username": "Missing Login", "password": "ConfiguredUserPassword!456"},
        {"login_id": "bad login", "username": "Bad Login", "password": "ConfiguredUserPassword!456"},
        {"login_id": "", "username": "Bad Login", "password": "ConfiguredUserPassword!456"},
    ]:
        response = client.post(
            "/dashboard/users",
            json=payload,
        )

        assert response.status_code == 422


def test_list_and_detail_return_safe_metadata() -> None:
    user = _user(role="USER")
    fake_session = _FakeSession([user])
    client = _client(fake_session)

    list_response = client.get("/dashboard/users")

    assert list_response.status_code == 200
    assert list_response.json()[0]["login_id"] == user.login_id
    _assert_safe_user_payload(list_response.json()[0])


def test_dashboard_users_aggregates_event_counts() -> None:
    alpha = _user(role="USER", login_id="alpha")
    beta = _user(role="USER", login_id="beta")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    alpha_blocked_at = now - timedelta(hours=4)
    alpha_masked_at = now - timedelta(hours=3)
    alpha_warned_at = now - timedelta(hours=2)
    alpha_allowed_at = now - timedelta(hours=1)
    beta_masked_at = now - timedelta(minutes=30)
    fake_session = _FakeSession(
        [alpha, beta],
        events=[
            _event(alpha, "BLOCK", alpha_blocked_at),
            _event(alpha, "MASK", alpha_masked_at),
            _event(alpha, "WARN", alpha_warned_at),
            _event(alpha, "ALLOW", alpha_allowed_at),
            _event(alpha, "BLOCK", now - timedelta(days=45)),
            _event(beta, "MASK", beta_masked_at),
        ],
    )
    client = _client(fake_session)

    response = client.get("/dashboard/users")

    assert response.status_code == 200
    rows = {row["login_id"]: row for row in response.json()}
    assert rows["alpha"]["event_count"] == 4
    assert rows["alpha"]["blocked_count"] == 1
    assert rows["alpha"]["masked_count"] == 1
    assert rows["alpha"]["warned_count"] == 1
    assert rows["alpha"]["last_event_at"] == _json_utc(alpha_allowed_at)
    assert rows["beta"]["event_count"] == 1
    assert rows["beta"]["blocked_count"] == 0
    assert rows["beta"]["masked_count"] == 1
    assert rows["beta"]["warned_count"] == 0
    assert rows["beta"]["last_event_at"] == _json_utc(beta_masked_at)
    for row in rows.values():
        _assert_no_sensitive_user_payload(row)


def test_role_patch_returns_404_for_missing_login_id() -> None:
    client = _client(_FakeSession())

    response = client.patch("/dashboard/users/missing-user/role", json={"role": "ADMIN"})

    assert response.status_code == 404


def test_role_and_status_patch_validate_values_and_update_existing_user() -> None:
    current_admin = _user(role="ADMIN", login_id="current-admin")
    user = _user(role="USER")
    fake_session = _FakeSession([current_admin, user])
    client = _client(fake_session, current_admin=current_admin)

    role_response = client.patch(f"/dashboard/users/{user.login_id}/role", json={"role": "ADMIN"})
    status_response = client.patch(f"/dashboard/users/{user.login_id}/status", json={"status": "DISABLED"})
    invalid_role_response = client.patch(f"/dashboard/users/{user.login_id}/role", json={"role": "OWNER"})
    invalid_status_response = client.patch(f"/dashboard/users/{user.login_id}/status", json={"status": "PENDING"})

    assert role_response.status_code == 200
    assert role_response.json()["role"] == "ADMIN"
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "DISABLED"
    assert invalid_role_response.status_code == 422
    assert invalid_status_response.status_code == 422
    assert fake_session.commits == 2


def test_cannot_remove_last_active_admin() -> None:
    current_admin = _user(role="ADMIN")
    fake_session = _FakeSession([current_admin])
    client = _client(fake_session, current_admin=current_admin)

    role_response = client.patch(f"/dashboard/users/{current_admin.login_id}/role", json={"role": "USER"})
    status_response = client.patch(f"/dashboard/users/{current_admin.login_id}/status", json={"status": "DISABLED"})

    assert role_response.status_code == 400
    assert status_response.status_code == 400
    assert current_admin.role == "ADMIN"
    assert current_admin.status == "ACTIVE"
    assert fake_session.commits == 0


def test_can_update_admin_when_another_active_admin_remains() -> None:
    current_admin = _user(role="ADMIN", login_id="current-admin")
    target_admin = _user(role="ADMIN", login_id="target-admin")
    fake_session = _FakeSession([current_admin, target_admin])
    client = _client(fake_session, current_admin=current_admin)

    role_response = client.patch(f"/dashboard/users/{target_admin.login_id}/role", json={"role": "USER"})
    target_admin.role = "ADMIN"
    status_response = client.patch(f"/dashboard/users/{target_admin.login_id}/status", json={"status": "DISABLED"})

    assert role_response.status_code == 200
    assert status_response.status_code == 200


def test_current_admin_cannot_demote_or_disable_self_even_when_another_admin_remains() -> None:
    current_admin = _user(role="ADMIN", login_id="current-admin")
    other_admin = _user(role="ADMIN", login_id="other-admin")
    fake_session = _FakeSession([current_admin, other_admin])
    client = _client(fake_session, current_admin=current_admin)

    role_response = client.patch(f"/dashboard/users/{current_admin.login_id}/role", json={"role": "USER"})
    status_response = client.patch(f"/dashboard/users/{current_admin.login_id}/status", json={"status": "DISABLED"})

    assert role_response.status_code == 400
    assert role_response.json()["detail"] == "admin cannot demote self"
    assert status_response.status_code == 400
    assert status_response.json()["detail"] == "admin cannot disable self"
    assert current_admin.role == "ADMIN"
    assert current_admin.status == "ACTIVE"
    assert fake_session.commits == 0


def test_dashboard_users_router_uses_dashboard_session_and_csrf_guards() -> None:
    read_paths = {"/dashboard/users"}
    mutation_paths = {
        "/dashboard/users",
        "/dashboard/users/{login_id}/role",
        "/dashboard/users/{login_id}/status",
    }

    for route in admin_users.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if path in read_paths and "GET" in methods:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            assert admin_users.require_dashboard_admin_session in dependency_calls
        if path in mutation_paths and methods.intersection({"POST", "PATCH"}):
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            assert admin_users.require_dashboard_admin_mutation in dependency_calls


def test_dashboard_user_mutation_requires_csrf_guard() -> None:
    client = _client(_FakeSession(), allow_mutation=False)

    response = client.patch("/dashboard/users/target/role", json={"role": "ADMIN"})

    assert response.status_code == 403


def test_legacy_admin_users_path_is_not_registered() -> None:
    app = FastAPI()
    app.include_router(admin_users.router)

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/admin/users" not in paths
    assert "/admin/users/{user_id}/role" not in paths
