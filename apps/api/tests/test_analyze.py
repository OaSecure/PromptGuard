import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import Index
from sqlalchemy.exc import IntegrityError

from app.core.tokens import create_access_token
from app.domain.types.policy import PolicyDecision
from app.models.events import AnalysisEvent, EventDetection, EventInput, IdempotencyKey
from app.models.filters import FilterRule
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session


class _FakeSession:
    def __init__(self, user, rules=None):
        self.user = user
        self.rules = rules
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.commit_error = None

    async def get(self, model, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None

    async def execute(self, statement):
        if "FROM idempotency_keys" in str(statement):
            return _FakeResult([])
        if self.rules is None:
            raise RuntimeError("filter rules not configured")
        return _FakeResult(self.rules)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1


class _FakeResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items

    def first(self):
        return self.items[0] if self.items else None


def _user(status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), login_id="user_123", role="USER", status=status, last_event_at=None)


def _user_with_login_id(login_id: str):
    return SimpleNamespace(id=uuid4(), login_id=login_id, role="USER", status="ACTIVE", last_event_at=None)


def _bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _filter_rule(**overrides):
    values = {
        "id": uuid4(),
        "origin": "custom",
        "kind": "keyword",
        "category": "Custom",
        "label": "Internal Project",
        "keyword": "Project Hermes",
        "placeholder": "INTERNAL_PROJECT",
        "severity": "high",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {"enabled": True},
        "version": 1,
    }
    values.update(overrides)
    return FilterRule(**values)


def _client(user=None, rules=None) -> tuple[TestClient, _FakeSession]:
    app = FastAPI()
    app.include_router(analyze_route.router)
    fake_session = _FakeSession(user, rules)

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(_request, exc):
        safe_errors = [
            {
                "loc": error.get("loc", ()),
                "msg": error.get("msg", "Invalid request"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    async def override_session():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), fake_session


def _text_input(input_id: str, content: str, source: str = "composer") -> dict:
    return {
        "input_id": input_id,
        "kind": "text",
        "source": source,
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "content_included": True,
    }


def _context(**overrides) -> dict:
    values = {
        "ai_service": "chatgpt",
        "ai_service_domain": "chatgpt.com",
        "page_url_origin": "https://chatgpt.com",
        "extension_version": "1.0.0",
        "browser": "chrome",
        "locale": "ko-KR",
    }
    values.update(overrides)
    return values


def _analyze_payload(*inputs: dict, **overrides) -> dict:
    values = {
        "client_request_id": "req_123",
        "filter_config_revision": "cfg_2026_06_04",
        "context": _context(),
        "inputs": list(inputs) or [_text_input("in_1", "hello")],
    }
    values.update(overrides)
    return values


def _main_app_or_skip():
    try:
        from app.main import app as main_app
    except TypeError as exc:
        if "on_startup" in str(exc):
            pytest.skip("local FastAPI/Starlette package mismatch prevents main app import")
        raise
    return main_app


def test_analyze_requires_credentials() -> None:
    client, _ = _client(_user())
    response = client.post("/prompts/analyze", json=_analyze_payload())

    assert response.status_code == 401


def test_event_metadata_models_do_not_define_raw_input_storage() -> None:
    forbidden_columns = {
        "content",
        "prompt",
        "raw_prompt",
        "file_content",
        "original_filename",
        "masked_prompt",
        "detected_raw_value",
    }

    assert forbidden_columns.isdisjoint(EventInput.__table__.columns.keys())
    assert forbidden_columns.isdisjoint(EventDetection.__table__.columns.keys())
    assert forbidden_columns.isdisjoint(AnalysisEvent.__table__.columns.keys())
    assert forbidden_columns.isdisjoint(IdempotencyKey.__table__.columns.keys())


def test_analyze_idempotency_schema_is_metadata_only() -> None:
    columns = set(IdempotencyKey.__table__.columns.keys())
    primary_key_columns = {column.name for column in IdempotencyKey.__table__.primary_key.columns}
    forbidden_columns = {
        "content",
        "prompt",
        "raw_prompt",
        "file_content",
        "original_filename",
        "masked_prompt",
        "detected_raw_value",
        "request_fingerprint",
        "prompt_hash",
        "prompt_hash_key_id",
    }

    assert {"login_id", "client_request_id", "event_id", "created_at", "expires_at"}.issubset(columns)
    assert primary_key_columns == {"login_id", "client_request_id"}
    assert forbidden_columns.isdisjoint(columns)


def test_event_metadata_schema_avoids_required_internal_identifiers() -> None:
    index_names = {index.name for index in EventDetection.__table__.indexes if isinstance(index, Index)}

    assert AnalysisEvent.__table__.c.prompt_hash.nullable
    assert AnalysisEvent.__table__.c.prompt_hash_key_id.nullable
    assert AnalysisEvent.__table__.c.filter_rule_set_version.nullable
    assert "ix_event_detections_filter_rule_id" in index_names


def test_analyze_rejects_disabled_user() -> None:
    user = _user(status="DISABLED")
    client, _ = _client(user)
    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(),
    )

    assert response.status_code == 403


def test_analyze_rejects_legacy_parallel_input_fields() -> None:
    user = _user()
    client, _ = _client(user)
    headers = _bearer_header(user.id)

    legacy_prompt = client.post("/prompts/analyze", headers=headers, json={"prompt": "hello"})
    legacy_input = client.post("/prompts/analyze", headers=headers, json={**_analyze_payload(), "input": "hello"})
    legacy_file = client.post("/prompts/analyze", headers=headers, json={**_analyze_payload(), "file": {"text": "hello"}})
    legacy_attachments = client.post(
        "/prompts/analyze",
        headers=headers,
        json={**_analyze_payload(), "attachments": [{"name": "secret.txt"}]},
    )

    assert legacy_prompt.status_code == 422
    assert legacy_input.status_code == 422
    assert legacy_file.status_code == 422
    assert legacy_attachments.status_code == 422


def test_analyze_accepts_inputs_bundle_and_returns_mvp_response_shape() -> None:
    user = _user()
    client, fake_session = _client(user)
    prompt = "\uacc4\uc57d\uc11c\uc5d0 \ud3ec\ud568\ub41c \uc5f0\ub77d\ucc98\ub97c \ud655\uc778\ud574\uc918"

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", prompt)),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Allow"
    assert body["risk_score"] == 0
    assert body["risk_level"] == "low"
    assert body["allow_original_send"] is True
    assert body["requires_user_confirmation"] is False
    assert body["detections"] == []
    assert body["input_results"] == [
        {
            "input_id": "in_1",
            "input_index": 0,
            "kind": "text",
            "source": "composer",
            "content_included": True,
            "content_scanned": True,
            "decision_basis": "no_detection",
        }
    ]
    assert body["content_unavailable_inputs"] == []
    assert "masked_prompt" not in body
    assert body["client_request_id"] == "req_123"
    assert body["filter_config_revision"] == "cfg_2026_06_04"
    assert fake_session.commits == 1
    assert user.last_event_at is not None


def test_analyze_rejects_duplicate_client_request_without_second_event(monkeypatch) -> None:
    user = _user()
    client, fake_session = _client(user)
    raw_prompt = "SECRET-DUPLICATE-PROMPT-DO-NOT-ECHO"

    async def fake_load_idempotency_key(session, login_id, client_request_id):
        return next(
            (
                item
                for item in session.added
                if isinstance(item, IdempotencyKey)
                and item.login_id == login_id
                and item.client_request_id == client_request_id
            ),
            None,
        )

    monkeypatch.setattr(analyze_route, "load_idempotency_key", fake_load_idempotency_key)

    first_response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", raw_prompt)),
    )
    duplicate_response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", raw_prompt)),
    )

    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    idempotency_keys = [item for item in fake_session.added if isinstance(item, IdempotencyKey)]
    duplicate_body = duplicate_response.json()
    encoded_duplicate = json.dumps(duplicate_body, ensure_ascii=False)
    assert first_response.status_code == 200
    assert duplicate_response.status_code == 409
    assert duplicate_body["detail"]["code"] == "DUPLICATE_REQUEST_RETRY_REQUIRED"
    assert raw_prompt not in encoded_duplicate
    assert "masked_prompt" not in encoded_duplicate
    assert len(events) == 1
    assert len(idempotency_keys) == 1
    assert idempotency_keys[0].login_id == user.login_id
    assert idempotency_keys[0].client_request_id == "req_123"
    assert idempotency_keys[0].event_id == events[0].id
    assert idempotency_keys[0].expires_at > datetime.now(timezone.utc)
    assert fake_session.commits == 1


def test_analyze_allows_same_client_request_id_for_different_login_ids(monkeypatch) -> None:
    user_a = _user_with_login_id("user_123")
    user_b = _user_with_login_id("user_456")
    client_a, session_a = _client(user_a)
    client_b, session_b = _client(user_b)

    async def fake_load_idempotency_key(session, login_id, client_request_id):
        return next(
            (
                item
                for candidate_session in (session_a, session_b)
                for item in candidate_session.added
                if isinstance(item, IdempotencyKey)
                and item.login_id == login_id
                and item.client_request_id == client_request_id
            ),
            None,
        )

    monkeypatch.setattr(analyze_route, "load_idempotency_key", fake_load_idempotency_key)

    response_a = client_a.post(
        "/prompts/analyze",
        headers=_bearer_header(user_a.id),
        json=_analyze_payload(client_request_id="req_shared"),
    )
    response_b = client_b.post(
        "/prompts/analyze",
        headers=_bearer_header(user_b.id),
        json=_analyze_payload(client_request_id="req_shared"),
    )

    events = [item for item in session_a.added + session_b.added if isinstance(item, AnalysisEvent)]
    idempotency_keys = [item for item in session_a.added + session_b.added if isinstance(item, IdempotencyKey)]
    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert len(events) == 2
    assert {(item.login_id, item.client_request_id) for item in idempotency_keys} == {
        ("user_123", "req_shared"),
        ("user_456", "req_shared"),
    }


def test_analyze_returns_duplicate_error_for_concurrent_idempotency_insert_conflict() -> None:
    user = _user()
    client, fake_session = _client(user)
    fake_session.commit_error = IntegrityError(
        statement="INSERT INTO idempotency_keys",
        params=None,
        orig=Exception("duplicate key value violates unique constraint idempotency_keys_pkey"),
    )

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(),
    )

    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    idempotency_keys = [item for item in fake_session.added if isinstance(item, IdempotencyKey)]
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DUPLICATE_REQUEST_RETRY_REQUIRED"
    assert len(events) == 1
    assert len(idempotency_keys) == 1
    assert fake_session.commits == 1
    assert fake_session.rollbacks == 1


def test_analyze_masks_email_and_phone_and_keeps_legacy_event_bridge_raw_free() -> None:
    user = _user()
    client, fake_session = _client(user)
    prompt = "Contact admin@example.com or 010-1234-5678."

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", prompt)),
    )

    body = response.json()
    encoded_body = json.dumps(body, ensure_ascii=False)
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    input_rows = [item for item in fake_session.added if isinstance(item, EventInput)]
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]

    assert response.status_code == 200
    assert body["action"] == "Mask"
    assert all(item["action"] == "Mask" for item in body["detections"])
    assert body["risk_score"] == 55
    assert body["risk_level"] == "medium"
    assert body["allow_original_send"] is False
    assert body["requires_user_confirmation"] is False
    assert body["masked_prompt"] == "Contact [EMAIL_1] or [PHONE_1]."
    assert {item["type"] for item in body["detections"]} == {"EMAIL", "PHONE"}
    assert {item["input_id"] for item in body["detections"]} == {"in_1"}
    assert {item["source"] for item in body["detections"]} == {"composer"}
    detections_by_type = {item["type"]: item for item in body["detections"]}
    assert detections_by_type["EMAIL"]["rule_id"] == "00000000-0000-4000-8000-000000000101"
    assert detections_by_type["EMAIL"]["detector_id"] == "EMAIL"
    assert detections_by_type["PHONE"]["rule_id"] == "00000000-0000-4000-8000-000000000102"
    assert detections_by_type["PHONE"]["detector_id"] == "PHONE"
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert "admin@example.com" not in encoded_body
    assert "010-1234-5678" not in encoded_body
    assert len(events) == 1
    assert events[0].action == "MASK"
    assert events[0].risk_score == 55
    assert events[0].login_id == "user_123"
    assert events[0].client_request_id == "req_123"
    assert events[0].prompt_hash is None
    assert events[0].prompt_hash_key_id is None
    assert events[0].filter_rule_set_version is None
    assert events[0].filter_config_revision == "cfg_2026_06_04"
    assert events[0].service == "chatgpt"
    assert events[0].service_domain == "chatgpt.com"
    assert events[0].platform == "chrome"
    assert len(input_rows) == 1
    assert input_rows[0].input_id == "in_1"
    assert input_rows[0].input_index == 0
    assert input_rows[0].kind == "text"
    assert input_rows[0].source == "composer"
    assert input_rows[0].content_included is True
    assert input_rows[0].content_scanned is True
    assert input_rows[0].decision_basis == "detection"
    assert len(detection_rows) == 2
    assert {item.type for item in detection_rows} == {"EMAIL", "PHONE"}
    assert {item.input_id for item in detection_rows} == {"in_1"}
    assert {item.input_source for item in detection_rows} == {"composer"}
    assert {item.action for item in detection_rows} == {"MASK"}
    assert {item.detector_id for item in detection_rows} == {"EMAIL", "PHONE"}
    assert all("raw" not in json.dumps(item.safe_evidence) for item in detection_rows)
    assert all(prompt not in json.dumps(item.safe_evidence) for item in detection_rows)
    assert fake_session.commits == 1


def test_analyze_masks_rrn_and_card_as_high_risk() -> None:
    user = _user()
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "rrn 900101-1234568 card 4111 1111 1111 1111")),
    )

    body = response.json()
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]

    assert response.status_code == 200
    assert body["action"] == "Mask"
    assert body["risk_score"] == 80
    assert body["risk_level"] == "high"
    assert body["masked_prompt"] == "rrn [RRN_1] card [CARD_1]"
    assert {item["type"] for item in body["detections"]} == {"RRN", "CARD"}
    assert {item.type for item in detection_rows} == {"RRN", "CARD"}


def test_analyze_accepts_content_unavailable_metadata_without_text_body() -> None:
    user = _user()
    client, fake_session = _client(user)
    unavailable_input = {
        "input_id": "in_2",
        "kind": "text",
        "source": "converted_paste",
        "size_bytes": 2_500_000,
        "content_included": False,
        "content_unavailable_reason": "oversized",
        "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "summarize this"), unavailable_input),
    )

    body = response.json()
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    input_rows = [item for item in fake_session.added if isinstance(item, EventInput)]
    encoded = json.dumps(body, ensure_ascii=False)
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["allow_original_send"] is False
    assert body["risk_level"] == "critical"
    assert body["input_results"][1] == {
        "input_id": "in_2",
        "input_index": 1,
        "kind": "text",
        "source": "converted_paste",
        "content_included": False,
        "content_scanned": False,
        "decision_basis": "content_unavailable",
        "content_unavailable_reason": "oversized",
        "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES",
    }
    assert body["content_unavailable_inputs"] == [
        {
            "input_id": "in_2",
            "input_index": 1,
            "kind": "text",
            "source": "converted_paste",
            "reason": "oversized",
            "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES",
        }
    ]
    assert "2_500_000" not in encoded
    assert len(events) == 1
    assert events[0].action == "BLOCK"
    assert len(input_rows) == 2
    assert input_rows[1].input_id == "in_2"
    assert input_rows[1].source == "converted_paste"
    assert input_rows[1].content_included is False
    assert input_rows[1].content_scanned is False
    assert input_rows[1].decision_basis == "content_unavailable"
    assert input_rows[1].content_unavailable_reason == "oversized"
    assert input_rows[1].limit_exceeded == "MAX_ANALYZE_REQUEST_BYTES"


def test_analyze_rejects_original_filename_in_attachment_metadata() -> None:
    user = _user()
    client, _ = _client(user)
    attachment_input = {
        "input_id": "in_2",
        "kind": "attachment_metadata",
        "source": "attachment_chip",
        "size_bytes": 300_000,
        "content_included": False,
        "metadata": {
            "original_filename": "secret-contract.png",
            "extension": "png",
            "mime": "image/png",
        },
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(attachment_input),
    )

    assert response.status_code == 422
    assert "secret-contract.png" not in json.dumps(response.json(), ensure_ascii=False)


def test_analyze_rejects_nested_filename_in_attachment_metadata() -> None:
    user = _user()
    client, _ = _client(user)
    attachment_input = {
        "input_id": "in_2",
        "kind": "attachment_metadata",
        "source": "attachment_chip",
        "size_bytes": 300_000,
        "content_included": False,
        "metadata": {
            "attachment": {
                "name": "nested-secret-contract.png",
                "extension": "png",
                "mime": "image/png",
            }
        },
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(attachment_input),
    )

    assert response.status_code == 422
    assert "nested-secret-contract.png" not in json.dumps(response.json(), ensure_ascii=False)


def test_analyze_respects_disabled_built_in_filter_rule() -> None:
    user = _user()
    client, fake_session = _client(
        user,
        rules=[
            _filter_rule(
                origin="built_in",
                kind="detector",
                category="PII",
                detector_key="EMAIL",
                severity="medium",
                action="MASK",
                enabled=False,
            )
        ],
    )

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "Contact admin@example.com")),
    )

    body = response.json()
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]
    assert response.status_code == 200
    assert body["action"] == "Allow"
    assert body["detections"] == []
    assert detection_rows == []


def test_analyze_records_custom_keyword_filter_metadata_without_raw_value() -> None:
    user = _user()
    rule = _filter_rule()
    client, fake_session = _client(user, rules=[rule])

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "Project Hermes should stay internal")),
    )

    body = response.json()
    encoded = json.dumps(body)
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    assert response.status_code == 200
    assert body["action"] == "Mask"
    assert body["risk_level"] == "high"
    assert body["detections"][0]["type"] == "INTERNAL_PROJECT"
    assert body["detections"][0]["source"] == "composer"
    assert body["detections"][0]["rule_id"] == str(rule.id)
    assert body["detections"][0]["detector_id"] == "INTERNAL_PROJECT"
    assert "Project Hermes" not in encoded
    assert detection_rows[0].source == "custom_keyword"
    assert detection_rows[0].input_id == "in_1"
    assert detection_rows[0].filter_rule_id == str(rule.id)
    assert detection_rows[0].detector_id == "INTERNAL_PROJECT"
    assert detection_rows[0].action == "MASK"
    assert "Project Hermes" not in json.dumps(detection_rows[0].safe_evidence)
    assert events[0].filter_config_revision == "cfg_2026_06_04"


def test_analyze_warn_action_requires_confirmation() -> None:
    user = _user()
    client, _ = _client(user, rules=[_filter_rule(action="WARN")])

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "Project Hermes should stay internal")),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Warn"
    assert body["allow_original_send"] is True
    assert body["requires_user_confirmation"] is True
    assert body["detections"][0]["action"] == "Warn"


def test_analyze_returns_business_context_matches_without_raw_spans() -> None:
    user = _user()
    rule = _filter_rule(
        kind="context_rule",
        category="Business",
        label="NDA Context",
        placeholder="BUSINESS_CONTEXT",
        severity="medium",
        action="WARN",
        keyword=None,
        config_json={
            "keyword_groups": {"contract": ["RAW_TARGET_ALPHA", "RAW_TARGET_BETA"]},
            "exclusion_keywords": [],
            "window_size": 80,
            "min_condition_count": 2,
            "sensitivity": "medium",
        },
    )
    client, fake_session = _client(user, rules=[rule])

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "RAW_TARGET_ALPHA RAW_TARGET_BETA amount is confidential.")),
    )

    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]
    encoded_event = json.dumps(detection_rows[0].__dict__, default=str, ensure_ascii=False)

    assert response.status_code == 200
    assert body["action"] == "Warn"
    assert body["requires_user_confirmation"] is True
    assert body["business_context_matches"] == [
        {
            "input_id": "in_1",
            "input_index": 0,
            "kind": "text",
            "source": "composer",
            "category": "Business",
            "reason_code": "CUSTOM_CONTEXT_RULE_NDA_CONTEXT",
            "match_count": 2,
            "matched_keywords": [
                f"rule:{rule.id}:group:cc8321d6375c:pattern:0",
                f"rule:{rule.id}:group:cc8321d6375c:pattern:1",
            ],
            "evidence_counts": {"matched_condition_count": 2},
        }
    ]
    assert body["detections"][0]["source"] == "composer"
    assert detection_rows[0].source == "custom_context_rule"
    assert detection_rows[0].matched_keywords == [
        f"rule:{rule.id}:group:cc8321d6375c:pattern:0",
        f"rule:{rule.id}:group:cc8321d6375c:pattern:1",
    ]
    assert detection_rows[0].evidence_counts == {"match_count": 2, "matched_condition_count": 2}
    assert "RAW_TARGET_ALPHA" not in encoded
    assert "RAW_TARGET_BETA" not in encoded
    assert "RAW_TARGET_ALPHA" not in encoded_event
    assert "RAW_TARGET_BETA" not in encoded_event
    assert "confidential" not in encoded
    assert "amount" not in encoded


def test_analyze_reports_detections_for_each_scannable_input() -> None:
    user = _user()
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(
            _text_input("composer_1", "Contact admin@example.com"),
            _text_input("paste_1", "Call 010-1234-5678", source="converted_paste"),
        ),
    )

    body = response.json()
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]
    input_rows = [item for item in fake_session.added if isinstance(item, EventInput)]
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["allow_original_send"] is False
    assert "masked_prompt" not in body
    assert {item["input_id"] for item in body["detections"]} == {"composer_1", "paste_1"}
    assert {item["source"] for item in body["detections"]} == {"composer", "converted_paste"}
    assert {item["decision_basis"] for item in body["input_results"]} == {"detection"}
    assert {(item.input_id, item.input_index, item.source, item.decision_basis) for item in input_rows} == {
        ("composer_1", 0, "composer", "detection"),
        ("paste_1", 1, "converted_paste", "detection"),
    }
    assert len(detection_rows) == 2
    assert {(item.input_id, item.input_index, item.input_source) for item in detection_rows} == {
        ("composer_1", 0, "composer"),
        ("paste_1", 1, "converted_paste"),
    }


def test_analyze_rejects_legacy_file_text_without_echoing_content() -> None:
    user = _user()
    client, fake_session = _client(user)
    file_text = "File secret admin@example.com"

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("file_1", file_text, source="file")),
    )

    encoded = response.text
    assert response.status_code == 422
    assert "admin@example.com" not in encoded
    assert fake_session.added == []


def test_analyze_blocks_unavailable_input_even_when_text_would_mask() -> None:
    user = _user()
    client, _ = _client(user)
    unavailable_input = {
        "input_id": "attachment_1",
        "kind": "unsupported_attachment",
        "source": "attachment_chip",
        "size_bytes": 500_000,
        "content_included": False,
        "content_unavailable_reason": "unsupported",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "Contact admin@example.com"), unavailable_input),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["risk_level"] == "critical"
    assert body["allow_original_send"] is False
    assert body["requires_user_confirmation"] is False
    assert "masked_prompt" not in body
    assert body["content_unavailable_inputs"] == [
        {
            "input_id": "attachment_1",
            "input_index": 1,
            "kind": "unsupported_attachment",
            "source": "attachment_chip",
            "reason": "unsupported",
        }
    ]
    assert body["input_results"][1]["decision_basis"] == "content_unavailable"


def test_analyze_applies_block_mask_warn_action_priority() -> None:
    user = _user()
    client, _ = _client(
        user,
        rules=[
            _filter_rule(keyword="warn marker", placeholder="WARN_MARKER", action="WARN", severity="low"),
            _filter_rule(keyword="mask marker", placeholder="MASK_MARKER", action="MASK", severity="medium"),
            _filter_rule(keyword="block marker", placeholder="BLOCK_MARKER", action="BLOCK", severity="critical"),
        ],
    )

    warn_response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "warn marker")),
    )
    mask_response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "warn marker mask marker")),
    )
    block_response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "warn marker mask marker block marker")),
    )

    assert warn_response.status_code == 200
    assert warn_response.json()["action"] == "Warn"
    assert warn_response.json()["requires_user_confirmation"] is True
    assert mask_response.status_code == 200
    assert mask_response.json()["action"] == "Mask"
    assert mask_response.json()["allow_original_send"] is False
    assert mask_response.json()["requires_user_confirmation"] is True
    assert block_response.status_code == 200
    assert block_response.json()["action"] == "Block"
    assert block_response.json()["risk_level"] == "critical"


def test_analyze_uses_policy_orchestrator_decision_without_recomputing_action() -> None:
    class ForcedBlockPolicy:
        def decide(self, _request):
            return PolicyDecision(
                action="block",
                reason_code="INTERNAL_POLICY_REASON_UNMAPPED",
                severity="high",
            )

    user = _user()
    client, _ = _client(user, rules=[])
    client.app.dependency_overrides[analyze_route.get_policy_orchestrator] = ForcedBlockPolicy

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", "ordinary text")),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "Block"
    assert response.json()["risk_score"] == 95


def test_analyze_rejects_mixed_legacy_file_text_before_partial_processing() -> None:
    user = _user()
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(
            _text_input("composer_1", "Contact admin@example.com"),
            _text_input("file_1", "Card 4111 1111 1111 1111", source="file"),
        ),
    )

    encoded = response.text
    assert response.status_code == 422
    assert "4111 1111 1111 1111" not in encoded
    assert fake_session.added == []


def test_analyze_validates_request_boundaries() -> None:
    user = _user()
    client, _ = _client(user)
    headers = _bearer_header(user.id)

    empty_inputs = client.post("/prompts/analyze", headers=headers, json=_analyze_payload(inputs=[]))
    bad_filter_revision = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload(filter_config_revision="../bad"),
    )
    bad_client_request_id = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload(client_request_id="not a safe id"),
    )
    secret_client_request_id = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload(client_request_id="req_ghp_seededsecret1234567890abcdef"),
    )
    secret_filter_revision = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload(filter_config_revision="cfg_sk-seededsecret1234567890abcdef"),
    )
    secret_input_id = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload(_text_input("in_AKIAIOSFODNN7EXAMPLE", "hello")),
    )
    wrong_size_bytes = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload({**_text_input("in_1", "hello"), "size_bytes": 99}),
    )

    assert empty_inputs.status_code == 422
    assert bad_filter_revision.status_code == 422
    assert bad_client_request_id.status_code == 422
    assert secret_client_request_id.status_code == 422
    assert secret_filter_revision.status_code == 422
    assert secret_input_id.status_code == 422
    assert wrong_size_bytes.status_code == 422
    encoded_errors = json.dumps(
        [
            secret_client_request_id.json(),
            secret_filter_revision.json(),
            secret_input_id.json(),
        ],
        ensure_ascii=False,
    )
    assert "ghp_seededsecret1234567890abcdef" not in encoded_errors
    assert "sk-seededsecret1234567890abcdef" not in encoded_errors
    assert "AKIAIOSFODNN7EXAMPLE" not in encoded_errors


def test_analyze_rejects_oversized_request_body_before_parsing() -> None:
    user = _user()
    client, _ = _client(user)
    oversized_content = "x" * (analyze_route.MAX_ANALYZE_REQUEST_BYTES + 1)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json={
            "client_request_id": "req_oversized",
            "filter_config_revision": "cfg_2026_06_04",
            "context": _context(),
            "inputs": [
                {
                    "input_id": "in_1",
                    "kind": "text",
                    "source": "composer",
                    "content": oversized_content,
                    "size_bytes": len(oversized_content),
                    "content_included": True,
                }
            ],
        },
    )

    assert response.status_code == 413
    assert "xxx" not in json.dumps(response.json())


def test_analyze_response_does_not_echo_raw_prompt_or_context_values() -> None:
    user = _user()
    raw_prompt = "SECRET-RAW-PROMPT-DO-NOT-ECHO"
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("in_1", raw_prompt)),
    )

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 200
    assert raw_prompt not in encoded_body
    assert "raw_prompt" not in encoded_body
    assert "detected_raw_value" not in encoded_body
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    assert len(events) == 1
    assert events[0].prompt_hash is None


def test_main_app_registers_analyze_inputs_schema_in_openapi() -> None:
    main_app = _main_app_or_skip()
    schema = main_app.openapi()

    assert "/prompts/analyze" in schema["paths"]
    assert "post" in schema["paths"]["/prompts/analyze"]
    operation = schema["paths"]["/prompts/analyze"]["post"]
    request_schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request_schema_name = request_schema_ref.rsplit("/", 1)[-1]
    request_schema = schema["components"]["schemas"][request_schema_name]
    assert "inputs" in request_schema["properties"]
    assert "prompt" not in request_schema["properties"]


def test_main_app_validation_errors_do_not_echo_raw_analyze_inputs() -> None:
    main_app = _main_app_or_skip()
    user = _user()
    raw_prompt = "SECRET-INVALID-PROMPT-DO-NOT-ECHO"
    raw_context_value = "private-context-value-do-not-echo"
    raw_secret = "ghp_seededsecret1234567890abcdef"

    async def override_session():
        yield _FakeSession(user)

    main_app.dependency_overrides[get_db_session] = override_session
    try:
        response = TestClient(main_app).post(
            "/prompts/analyze",
            headers=_bearer_header(user.id),
            json=_analyze_payload(
                {
                    "input_id": "in_1",
                    "kind": "text",
                    "source": "composer",
                    "content": raw_prompt,
                    "size_bytes": 99,
                    "content_included": True,
                },
                context=_context(ai_service=f"chatgpt-{raw_secret}", browser=raw_context_value),
            ),
        )
    finally:
        main_app.dependency_overrides.pop(get_db_session, None)

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 422
    assert raw_prompt not in encoded_body
    assert raw_context_value not in encoded_body
    assert raw_secret not in encoded_body
