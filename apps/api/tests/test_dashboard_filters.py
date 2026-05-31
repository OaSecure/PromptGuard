import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.events import AnalysisEvent
from app.models.filters import FilterRule, FilterRuleVersion
from app.routes import dashboard_filters


class _FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _FakeResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return _FakeScalars(self.items)


class _FakeSession:
    def __init__(self, rules=None):
        self.rules = rules or []
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, _statement):
        return _FakeResult([rule for rule in self.rules if rule.archived_at is None])

    async def get(self, model, item_id):
        if model is FilterRule:
            return next((rule for rule in self.rules if rule.id == item_id), None)
        return None

    def add(self, item):
        self.added.append(item)
        if isinstance(item, FilterRule):
            self.rules.append(item)

    async def commit(self):
        self.commits += 1

    async def refresh(self, item):
        self.refreshed.append(item)


def _admin(role: str = "ADMIN"):
    return SimpleNamespace(id=uuid4(), role=role, status="ACTIVE")


def _rule(**overrides):
    values = {
        "id": uuid4(),
        "origin": "custom",
        "kind": "keyword",
        "category": "Custom",
        "label": "Internal Strategy",
        "description": "Detects configured keyword.",
        "keyword": "internal strategy",
        "placeholder": "CUSTOM_KEYWORD",
        "severity": "medium",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {
            "category": True,
            "label": True,
            "description": True,
            "keyword": True,
            "pattern": True,
            "placeholder": True,
            "severity": True,
            "action": True,
            "enabled": True,
            "config_json": True,
        },
        "config_json": {"keywords": ["internal strategy"], "exclusion_keywords": []},
        "version": 1,
    }
    values.update(overrides)
    return FilterRule(**values)


def _built_in_rule(**overrides):
    return _rule(
        origin="built_in",
        kind="detector",
        category="PII",
        label="Email Address",
        detector_key="EMAIL",
        keyword=None,
        placeholder="EMAIL",
        editable_fields={"severity": True, "action": True, "enabled": True},
        config_json=None,
        **overrides,
    )


def _client(fake_session: _FakeSession, *, role: str = "ADMIN") -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_filters.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return _admin(role=role)

    app.dependency_overrides[dashboard_filters.get_db_session] = override_session
    app.dependency_overrides[dashboard_filters.require_admin] = override_admin
    return TestClient(app)


def test_dashboard_filters_without_credentials_returns_401() -> None:
    app = FastAPI()
    app.include_router(dashboard_filters.router)

    async def override_session():
        yield _FakeSession()

    app.dependency_overrides[dashboard_filters.get_db_session] = override_session
    response = TestClient(app).get("/dashboard/filters")

    assert response.status_code == 401


def test_dashboard_filters_user_access_is_forbidden() -> None:
    response = _client(_FakeSession(), role="USER").get("/dashboard/filters")

    assert response.status_code == 403


def test_dashboard_filters_list_uses_origin_alias_without_source() -> None:
    response = _client(_FakeSession([_built_in_rule(), _rule(kind="context_rule", config_json={
        "keyword_groups": {"business": ["internal strategy"]},
        "exclusion_keywords": [],
        "window_size": 80,
        "min_condition_count": 1,
        "sensitivity": "medium",
    })])).get("/dashboard/filters")
    body = response.json()

    assert response.status_code == 200
    assert {item["origin"] for item in body} == {"built_in", "custom"}
    assert any(item["kind"] == "context_rule" for item in body)
    assert all("source" not in item for item in body)
    assert all("editable_fields" in item for item in body)


def test_dashboard_filters_preserves_existing_rule_id_type() -> None:
    rule = _rule()
    response = _client(_FakeSession([rule])).get(f"/dashboard/filters/{rule.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(rule.id)


def test_dashboard_filters_create_custom_keyword_and_invalid_regex() -> None:
    fake_session = _FakeSession()
    created = _client(fake_session).post(
        "/dashboard/filters",
        json={
            "kind": "keyword",
            "category": "Custom",
            "label": "Internal Strategy",
            "placeholder": "CUSTOM_KEYWORD",
            "severity": "medium",
            "action": "MASK",
            "config_json": {"keywords": ["internal strategy"], "exclusion_keywords": []},
        },
    )
    invalid_regex = _client(_FakeSession()).post(
        "/dashboard/filters",
        json={
            "kind": "regex",
            "category": "Custom",
            "label": "Bad Regex",
            "pattern": "[",
            "severity": "medium",
            "action": "WARN",
        },
    )

    assert created.status_code == 201
    assert created.json()["origin"] == "custom"
    assert any(isinstance(item, FilterRuleVersion) and item.change_type == "create" for item in fake_session.added)
    assert invalid_regex.status_code == 422


def test_dashboard_filters_validates_context_rule_config() -> None:
    empty_config = _client(_FakeSession()).post(
        "/dashboard/filters",
        json={
            "kind": "context_rule",
            "category": "Business",
            "label": "Empty Context",
            "placeholder": "CONTEXT_RULE",
            "severity": "medium",
            "action": "WARN",
            "config_json": {},
        },
    )
    invalid_sensitivity = _client(_FakeSession()).post(
        "/dashboard/filters",
        json={
            "kind": "context_rule",
            "category": "Business",
            "label": "Invalid Context",
            "placeholder": "CONTEXT_RULE",
            "severity": "medium",
            "action": "WARN",
            "config_json": {
                "keyword_groups": {"business": ["internal strategy"]},
                "exclusion_keywords": [],
                "window_size": 80,
                "min_condition_count": 1,
                "sensitivity": "maximum",
            },
        },
    )

    assert empty_config.status_code == 422
    assert invalid_sensitivity.status_code == 422


def test_dashboard_filters_built_in_forbidden_fields_and_archive_are_rejected() -> None:
    rule = _built_in_rule()
    client = _client(_FakeSession([rule]))

    patch_response = client.patch(f"/dashboard/filters/{rule.id}", json={"label": "Changed"})
    delete_response = client.delete(f"/dashboard/filters/{rule.id}")

    assert patch_response.status_code == 422
    assert delete_response.status_code == 422


def test_dashboard_filters_custom_archive_sets_enabled_false() -> None:
    rule = _rule()
    fake_session = _FakeSession([rule])
    response = _client(fake_session).delete(f"/dashboard/filters/{rule.id}")

    assert response.status_code == 204
    assert rule.archived_at is not None
    assert rule.enabled is False
    assert any(isinstance(item, FilterRuleVersion) and item.change_type == "archive" for item in fake_session.added)


def test_dashboard_filters_enable_disable_keeps_existing_version_behavior() -> None:
    rule = _rule()
    fake_session = _FakeSession([rule])
    response = _client(fake_session).patch(f"/dashboard/filters/{rule.id}/disable")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert rule.version == 2
    assert any(isinstance(item, FilterRuleVersion) and item.change_type == "disable" for item in fake_session.added)


def test_dashboard_filter_dry_run_returns_safe_single_rule_metadata() -> None:
    rule = _rule()
    raw_sample = "next quarter plan says internal strategy must stay private"
    fake_session = _FakeSession([rule])
    response = _client(fake_session).post(
        "/dashboard/filters/dry-run",
        json={"rule_id": str(rule.id), "sample_text": raw_sample},
    )
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["matched"] is True
    assert body["expected_action"] == "MASK"
    assert body["sample_persisted"] is False
    assert body["matched_keywords"] == ["internal strategy"]
    assert raw_sample not in encoded
    assert "next quarter plan" not in encoded
    assert not any(isinstance(item, AnalysisEvent) for item in fake_session.added)


def test_dashboard_filter_dry_run_oversized_sample_returns_safe_413() -> None:
    rule = _rule()
    raw_sample = "SECRET-DASHBOARD-OVERSIZED-" + ("x" * 20_001)
    response = _client(_FakeSession([rule])).post(
        "/dashboard/filters/dry-run",
        json={"rule_id": str(rule.id), "sample_text": raw_sample},
    )
    encoded = json.dumps(response.json())

    assert response.status_code == 413
    assert "SECRET-DASHBOARD-OVERSIZED" not in encoded
    assert "sample_text" not in encoded


def test_dashboard_filter_dry_run_supports_draft_rule_without_persisting() -> None:
    fake_session = _FakeSession()
    response = _client(fake_session).post(
        "/dashboard/filters/dry-run",
        json={
            "sample_text": "review code name alpha before release",
            "draft_rule": {
                "kind": "keyword",
                "category": "Custom",
                "label": "Code Name",
                "placeholder": "CODE_NAME",
                "severity": "medium",
                "action": "WARN",
                "config_json": {"keywords": ["code name"], "exclusion_keywords": []},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert response.json()["sample_persisted"] is False
    assert not any(isinstance(item, FilterRule) for item in fake_session.added)
