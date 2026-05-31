import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.filters import FilterRule, FilterRuleVersion
from app.routes import filters


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


def _admin():
    return SimpleNamespace(id=uuid4(), role="ADMIN", status="ACTIVE")


def _rule(**overrides):
    values = {
        "id": uuid4(),
        "source": "custom",
        "kind": "keyword",
        "category": "Custom",
        "label": "Internal Project",
        "description": "Detects internal project name.",
        "keyword": "Project Hermes",
        "placeholder": "INTERNAL_PROJECT",
        "severity": "high",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {
            "label": True,
            "keyword": True,
            "severity": True,
            "action": True,
            "enabled": True,
            "config_json": True,
        },
        "version": 1,
    }
    values.update(overrides)
    return FilterRule(**values)


def _client(fake_session: _FakeSession, *, allow_admin: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(filters.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if not allow_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return _admin()

    app.dependency_overrides[filters.get_db_session] = override_session
    app.dependency_overrides[filters.require_admin] = override_admin
    return TestClient(app)


def test_filters_require_admin_access() -> None:
    response = _client(_FakeSession(), allow_admin=False).get("/filters")

    assert response.status_code == 403


def test_list_filters_returns_safe_rule_metadata() -> None:
    rule = _rule()
    response = _client(_FakeSession([rule])).get("/filters")
    body = response.json()
    encoded = json.dumps(body)

    assert response.status_code == 200
    assert body[0]["id"] == str(rule.id)
    assert body[0]["editable_fields"]["enabled"] is True
    assert "password_hash" not in encoded
    assert "raw_prompt" not in encoded


def test_create_custom_keyword_rule_records_version() -> None:
    fake_session = _FakeSession()
    response = _client(fake_session).post(
        "/filters",
        json={
            "kind": "keyword",
            "category": "Custom",
            "label": "Internal Project",
            "keyword": "Project Hermes",
            "placeholder": "INTERNAL_PROJECT",
            "severity": "high",
            "action": "MASK",
        },
    )

    assert response.status_code == 201
    assert response.json()["source"] == "custom"
    assert any(isinstance(item, FilterRule) for item in fake_session.added)
    assert any(isinstance(item, FilterRuleVersion) and item.change_type == "create" for item in fake_session.added)
    assert fake_session.commits == 1


def test_regex_rule_requires_valid_pattern() -> None:
    response = _client(_FakeSession()).post(
        "/filters",
        json={
            "kind": "regex",
            "category": "Custom",
            "label": "Bad Regex",
            "pattern": "[",
            "severity": "medium",
            "action": "WARN",
        },
    )

    assert response.status_code == 400


def test_built_in_rule_blocks_non_editable_fields() -> None:
    rule = _rule(
        source="built_in",
        kind="detector",
        detector_key="EMAIL",
        editable_fields={"severity": True, "action": True, "enabled": True},
    )
    response = _client(_FakeSession([rule])).patch(f"/filters/{rule.id}", json={"label": "Changed"})

    assert response.status_code == 400
    assert response.json()["detail"] == "label is not editable"


def test_disable_rule_increments_version_and_records_audit() -> None:
    rule = _rule()
    fake_session = _FakeSession([rule])
    response = _client(fake_session).patch(f"/filters/{rule.id}/disable")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert rule.version == 2
    assert any(isinstance(item, FilterRuleVersion) and item.change_type == "disable" for item in fake_session.added)


def test_dry_run_returns_metadata_without_raw_sample() -> None:
    raw_sample = "Project Hermes is secret"
    response = _client(_FakeSession([_rule()])).post("/filters/dry-run", json={"sample_text": raw_sample})
    encoded = json.dumps(response.json())

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert response.json()["expected_action"] == "MASK"
    assert "Project Hermes" not in encoded
    assert "sample_text" not in encoded
