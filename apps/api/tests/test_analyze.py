import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.models.events import AnalysisEvent, EventDetection
from app.models.filters import FilterRule
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session


class _FakeSession:
    def __init__(self, user, rules=None):
        self.user = user
        self.rules = rules
        self.added = []
        self.commits = 0

    async def get(self, model, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None

    async def execute(self, _statement):
        if self.rules is None:
            raise RuntimeError("filter rules not configured")
        return _FakeResult(self.rules)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


class _FakeResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


def _user(status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role="USER", status=status, last_event_at=None)


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
    prompt = "계약서에 포함된 연락처를 확인해줘"

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


def test_analyze_masks_email_and_phone_and_persists_safe_metadata() -> None:
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
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]

    assert response.status_code == 200
    assert body["action"] == "Mask"
    assert body["risk_score"] == 55
    assert body["risk_level"] == "medium"
    assert body["allow_original_send"] is False
    assert body["requires_user_confirmation"] is False
    assert body["masked_prompt"] == "Contact [EMAIL_1] or [PHONE_1]."
    assert {item["type"] for item in body["detections"]} == {"EMAIL", "PHONE"}
    assert {item["input_id"] for item in body["detections"]} == {"in_1"}
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert "admin@example.com" not in encoded_body
    assert "010-1234-5678" not in encoded_body
    assert len(events) == 1
    assert events[0].action == "MASK"
    assert events[0].risk_score == 55
    assert events[0].prompt_hash != prompt
    assert events[0].service == "chatgpt"
    assert events[0].service_domain == "chatgpt.com"
    assert events[0].platform == "chrome"
    assert len(detection_rows) == 2
    assert {item.type for item in detection_rows} == {"EMAIL", "PHONE"}
    assert all("raw" not in json.dumps(item.safe_evidence) for item in detection_rows)
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
    client, fake_session = _client(user, rules=[_filter_rule()])

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
    assert "Project Hermes" not in encoded
    assert detection_rows[0].source == "custom_keyword"
    assert "Project Hermes" not in json.dumps(detection_rows[0].safe_evidence)
    assert events[0].filter_rule_set_version == "cfg_2026_06_04"


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
    wrong_size_bytes = client.post(
        "/prompts/analyze",
        headers=headers,
        json=_analyze_payload({**_text_input("in_1", "hello"), "size_bytes": 99}),
    )

    assert empty_inputs.status_code == 422
    assert bad_filter_revision.status_code == 422
    assert bad_client_request_id.status_code == 422
    assert wrong_size_bytes.status_code == 422


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
    assert events[0].prompt_hash != raw_prompt


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
