import json
from types import SimpleNamespace
from uuid import uuid4

from app.models.policy_settings import PolicySettings
from app.routes import dashboard_policy_settings
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


class _FakeScalars:
    def __init__(self, items):
        self.items = items

    def first(self):
        return self.items[0] if self.items else None


class _FakeResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return _FakeScalars(self.items)


class _FakeSession:
    def __init__(self, settings=None):
        self.settings = settings
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, _statement):
        return _FakeResult([self.settings] if self.settings is not None else [])

    def add(self, item):
        self.added.append(item)
        if isinstance(item, PolicySettings):
            self.settings = item

    async def commit(self):
        self.commits += 1

    async def refresh(self, item):
        self.refreshed.append(item)


def _admin(role: str = "ADMIN"):
    return SimpleNamespace(id=uuid4(), login_id="admin@example.test", role=role, status="ACTIVE")


def _client(
    fake_session: _FakeSession,
    *,
    role: str = "ADMIN",
    allow_session: bool = True,
    allow_mutation: bool = True,
) -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_policy_settings.router)

    async def override_session():
        yield fake_session

    async def override_dashboard_session():
        if not allow_session or role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return _admin(role=role)

    async def override_dashboard_mutation():
        if not allow_mutation:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token required")
        if role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return _admin(role=role)

    app.dependency_overrides[dashboard_policy_settings.get_db_session] = override_session
    app.dependency_overrides[dashboard_policy_settings.require_dashboard_admin_session] = override_dashboard_session
    app.dependency_overrides[dashboard_policy_settings.require_dashboard_admin_mutation] = override_dashboard_mutation
    return TestClient(app)


def test_dashboard_policy_settings_missing_row_returns_v353_defaults_without_persisting() -> None:
    fake_session = _FakeSession()
    response = _client(fake_session).get("/dashboard/policy-settings")
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "context_classifier_action": "WARN",
        "content_not_scanned_action": "WARN",
        "parser_or_ocr_failure_action": "WARN",
        "empty_input_action": "ALLOW",
        "unsupported_mask_fallback_action": "BLOCK",
        "version": 0,
    }
    assert fake_session.commits == 0
    assert fake_session.added == []


def test_dashboard_policy_settings_update_persists_enums_and_safe_metadata_only() -> None:
    fake_session = _FakeSession()
    response = _client(fake_session).patch(
        "/dashboard/policy-settings",
        json={
            "context_classifier_action": "BLOCK",
            "content_not_scanned_action": "WARN",
            "parser_or_ocr_failure_action": "WARN",
            "empty_input_action": "ALLOW",
            "unsupported_mask_fallback_action": "WARN",
        },
    )
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["context_classifier_action"] == "BLOCK"
    assert body["unsupported_mask_fallback_action"] == "WARN"
    assert body["version"] == 1
    assert fake_session.commits == 1
    assert fake_session.settings is not None
    assert fake_session.settings.updated_by_user_id is not None
    for forbidden in (
        "raw_prompt",
        "file_content",
        "extracted_text",
        "original_filename",
        "raw_detected_value",
        "embedding_vector",
        "logits",
        "masked_prompt",
    ):
        assert forbidden not in encoded


def test_dashboard_policy_settings_rejects_invalid_action_and_immutable_fields() -> None:
    invalid_action = _client(_FakeSession()).patch(
        "/dashboard/policy-settings",
        json={"context_classifier_action": "MASK"},
    )
    immutable_field = _client(_FakeSession()).patch(
        "/dashboard/policy-settings",
        json={"action_priority": ["allow", "warn", "mask", "block"]},
    )

    assert invalid_action.status_code == 422
    assert immutable_field.status_code == 422


def test_dashboard_policy_settings_unsupported_mask_fallback_cannot_allow_or_mask() -> None:
    allow_response = _client(_FakeSession()).patch(
        "/dashboard/policy-settings",
        json={"unsupported_mask_fallback_action": "ALLOW"},
    )
    mask_response = _client(_FakeSession()).patch(
        "/dashboard/policy-settings",
        json={"unsupported_mask_fallback_action": "MASK"},
    )

    assert allow_response.status_code == 422
    assert mask_response.status_code == 422


def test_dashboard_policy_settings_mutation_requires_dashboard_csrf_guard() -> None:
    response = _client(_FakeSession(), allow_mutation=False).patch(
        "/dashboard/policy-settings",
        json={"context_classifier_action": "WARN"},
    )

    assert response.status_code == 403


def test_dashboard_policy_settings_user_access_is_forbidden() -> None:
    read_response = _client(_FakeSession(), role="USER").get("/dashboard/policy-settings")
    update_response = _client(_FakeSession(), role="USER").patch(
        "/dashboard/policy-settings",
        json={"context_classifier_action": "WARN"},
    )

    assert read_response.status_code == 403
    assert update_response.status_code == 403


def test_dashboard_policy_settings_router_uses_dashboard_session_and_csrf_guards() -> None:
    for route in dashboard_policy_settings.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        if path == "/dashboard/policy-settings" and "GET" in methods:
            assert dashboard_policy_settings.require_dashboard_admin_session in dependency_calls
        if path == "/dashboard/policy-settings" and "PATCH" in methods:
            assert dashboard_policy_settings.require_dashboard_admin_mutation in dependency_calls
