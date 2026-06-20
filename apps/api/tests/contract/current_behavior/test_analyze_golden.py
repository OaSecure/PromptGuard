from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.models.events import AnalysisEvent, EventDetection, EventInput, IdempotencyKey
from app.models.filters import FilterRule
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session
from tests.contract.current_behavior.snapshot_helpers import assert_matches_snapshot, assert_storage_privacy

USER_ID = UUID("10000000-0000-0000-0000-000000000001")
RULE_ID = UUID("20000000-0000-0000-0000-000000000001")
USER = SimpleNamespace(id=USER_ID, login_id="snapshot_user", role="USER", status="ACTIVE", last_event_at=None)


class FakeResult:
    def __init__(self, items): self.items = items
    def scalars(self): return self
    def all(self): return self.items
    def first(self): return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, rules): self.rules, self.added, self.commits, self.rollbacks = rules, [], 0, 0
    async def get(self, _model, user_id): return USER if user_id == USER_ID else None
    async def execute(self, statement): return FakeResult([] if "FROM idempotency_keys" in str(statement) else self.rules)
    def add(self, item): self.added.append(item)
    async def commit(self): self.commits += 1
    async def rollback(self): self.rollbacks += 1


def client_for(rules):
    app, session = FastAPI(), FakeSession(rules)
    app.include_router(analyze_route.router)
    async def override_session(): yield session
    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), session


def rule(action):
    return FilterRule(id=RULE_ID, origin="custom", kind="keyword", category="Custom", label="Snapshot marker",
                      keyword="snapshot marker", placeholder="SNAPSHOT_MARKER", severity="critical" if action == "BLOCK" else "high",
                      action=action, enabled=True, editable_fields={"enabled": True}, version=1)


def text(input_id, content, source="composer"):
    return {"input_id": input_id, "kind": "text", "source": source, "size_bytes": len(content.encode()),
            "content_included": True, "content": content}


def payload(inputs):
    return {"client_request_id": "snapshot_request", "filter_config_revision": "snapshot_config",
            "context": {"ai_service": "chatgpt", "ai_service_domain": "chatgpt.com", "page_url_origin": "https://chatgpt.com",
                        "extension_version": "0.4.0", "browser": "chrome", "locale": "ko-KR"}, "inputs": inputs}


def project_rows(session):
    event = next(item for item in session.added if isinstance(item, AnalysisEvent))
    inputs = sorted((item for item in session.added if isinstance(item, EventInput)), key=lambda item: item.input_index)
    detections = sorted((item for item in session.added if isinstance(item, EventDetection)), key=lambda item: (item.input_index, item.type))
    event_keys = ["login_id", "client_request_id", "action", "risk_score", "risk_level", "filter_config_revision", "service", "service_domain", "platform"]
    input_keys = ["input_id", "input_index", "kind", "source", "size_bytes", "content_included", "content_scanned", "decision_basis", "content_unavailable_reason", "limit_exceeded"]
    detection_keys = ["input_id", "input_index", "kind", "input_source", "action", "placeholder", "category", "type", "source", "severity", "confidence", "count", "reason_code", "match_count", "safe_evidence", "matched_keywords", "evidence_counts"]
    return {"event": {key: getattr(event, key) for key in event_keys},
            "inputs": [{key: getattr(row, key) for key in input_keys} for row in inputs],
            "detections": [{key: getattr(row, key) for key in detection_keys} for row in detections],
            "commits": session.commits, "rollbacks": session.rollbacks,
            "idempotency_rows": sum(isinstance(item, IdempotencyKey) for item in session.added)}


def post_snapshot(rules, inputs):
    client, session = client_for(rules)
    token, _ = create_access_token(USER_ID)
    response = client.post("/prompts/analyze", headers={"Authorization": f"Bearer {token}"}, json=payload(inputs))
    assert response.status_code == 200
    return {"response": response.json(), "storage": project_rows(session)}


@pytest.mark.parametrize(("action", "fixture"), [("ALLOW", "allow_basic_text.json"), ("WARN", "warn_basic_text.json"),
                                                    ("MASK", "mask_composer.json"), ("BLOCK", "block_basic_text.json")])
def test_current_action_response_and_event_snapshots(action, fixture):
    rules = [] if action == "ALLOW" else [rule(action)]
    content = "ordinary Korean 한글" if action == "ALLOW" else "snapshot marker"
    actual = post_snapshot(rules, [text("input_1", content)])
    assert_storage_privacy(actual["storage"])
    assert_matches_snapshot(fixture, actual)


def test_current_multiple_and_metadata_only_snapshot():
    inputs = [text("composer_1", "ordinary"), text("paste_1", "snapshot marker", "converted_paste"),
              {"input_id": "chip_1", "kind": "attachment_metadata", "source": "attachment_chip", "size_bytes": 42,
               "content_included": False, "metadata": {"extension": "pdf", "mime": "application/pdf"}}]
    actual = post_snapshot([rule("WARN")], inputs)
    assert_storage_privacy(actual["storage"])
    assert_matches_snapshot("warn_multiple_metadata_only.json", actual)
