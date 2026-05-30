import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app as main_app
from app.core.tokens import create_access_token
from app.models.events import AnalysisEvent, EventDetection
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.added = []
        self.commits = 0

    async def get(self, model, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


def _user(status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role="USER", status=status, last_event_at=None)


def _bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _client(user=None) -> tuple[TestClient, _FakeSession]:
    app = FastAPI()
    app.include_router(analyze_route.router)
    fake_session = _FakeSession(user)

    async def override_session():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), fake_session


def test_analyze_requires_credentials() -> None:
    client, _ = _client(_user())
    response = client.post("/prompts/analyze", json={"prompt": "hello"})

    assert response.status_code == 401


def test_analyze_rejects_disabled_user() -> None:
    user = _user(status="DISABLED")
    client, _ = _client(user)
    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json={"prompt": "hello"},
    )

    assert response.status_code == 403


def test_analyze_accepts_schema_and_returns_safe_context() -> None:
    user = _user()
    client_request_id = str(uuid4())
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json={
            "prompt": "계약서에 포함된 연락처를 확인해줘",
            "context": {"platform": "chatgpt", "source": "extension"},
            "filter_config_version": "default:2026-05-30",
            "client_request_id": client_request_id,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "accepted"
    assert body["action"] == "ALLOW"
    assert body["risk_score"] == 0
    assert body["risk_level"] == "low"
    assert body["allow_original_send"] is True
    assert body["requires_justification"] is False
    assert body["detections"] == []
    assert "masked_prompt" not in body
    assert body["prompt_length"] == len("계약서에 포함된 연락처를 확인해줘")
    assert body["client_request_id"] == client_request_id
    assert body["filter_config_version"] == "default:2026-05-30"
    assert body["workspace_context"] == {"source": "authenticated_user", "user_id": str(user.id)}
    assert fake_session.commits == 1
    assert user.last_event_at is not None


def test_analyze_masks_email_and_phone_and_persists_safe_metadata() -> None:
    user = _user()
    client, fake_session = _client(user)
    prompt = "Contact admin@example.com or 010-1234-5678."

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json={"prompt": prompt, "context": {"service": "ChatGPT", "platform": "web"}},
    )

    body = response.json()
    encoded_body = json.dumps(body, ensure_ascii=False)
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]

    assert response.status_code == 200
    assert body["action"] == "MASK"
    assert body["risk_score"] == 55
    assert body["risk_level"] == "medium"
    assert body["allow_original_send"] is False
    assert body["masked_prompt"] == "Contact [EMAIL_1] or [PHONE_1]."
    assert {item["type"] for item in body["detections"]} == {"EMAIL", "PHONE"}
    assert "admin@example.com" not in encoded_body
    assert "010-1234-5678" not in encoded_body
    assert len(events) == 1
    assert events[0].action == "MASK"
    assert events[0].risk_score == 55
    assert events[0].prompt_hash != prompt
    assert events[0].service == "ChatGPT"
    assert events[0].platform == "web"
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
        json={"prompt": "rrn 900101-1234568 card 4111 1111 1111 1111"},
    )

    body = response.json()
    detection_rows = [item for item in fake_session.added if isinstance(item, EventDetection)]

    assert response.status_code == 200
    assert body["action"] == "MASK"
    assert body["risk_score"] == 80
    assert body["risk_level"] == "high"
    assert body["masked_prompt"] == "rrn [RRN_1] card [CARD_1]"
    assert {item["type"] for item in body["detections"]} == {"RRN", "CARD"}
    assert {item.type for item in detection_rows} == {"RRN", "CARD"}


def test_analyze_validates_request_boundaries() -> None:
    user = _user()
    client, _ = _client(user)
    headers = _bearer_header(user.id)

    blank_prompt = client.post("/prompts/analyze", headers=headers, json={"prompt": "   "})
    bad_filter_version = client.post(
        "/prompts/analyze",
        headers=headers,
        json={"prompt": "hello", "filter_config_version": "../bad"},
    )
    bad_client_request_id = client.post(
        "/prompts/analyze",
        headers=headers,
        json={"prompt": "hello", "client_request_id": "not-a-uuid"},
    )
    oversized_context = client.post(
        "/prompts/analyze",
        headers=headers,
        json={"prompt": "hello", "context": {"blob": "x" * 4_200}},
    )

    assert blank_prompt.status_code == 422
    assert bad_filter_version.status_code == 422
    assert bad_client_request_id.status_code == 422
    assert oversized_context.status_code == 422


def test_analyze_response_does_not_echo_raw_prompt_or_context_values() -> None:
    user = _user()
    raw_prompt = "SECRET-RAW-PROMPT-DO-NOT-ECHO"
    raw_context_value = "private-context-value"
    client, fake_session = _client(user)

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json={"prompt": raw_prompt, "context": {"note": raw_context_value}},
    )

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 200
    assert raw_prompt not in encoded_body
    assert raw_context_value not in encoded_body
    assert "raw_prompt" not in encoded_body
    assert "masked_prompt" not in encoded_body
    assert "detected_raw_value" not in encoded_body
    events = [item for item in fake_session.added if isinstance(item, AnalysisEvent)]
    assert len(events) == 1
    assert events[0].prompt_hash != raw_prompt


def test_main_app_registers_analyze_route_in_openapi() -> None:
    schema = main_app.openapi()

    assert "/prompts/analyze" in schema["paths"]
    assert "post" in schema["paths"]["/prompts/analyze"]


def test_main_app_validation_errors_do_not_echo_raw_prompt_or_context_values() -> None:
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
            json={
                "prompt": raw_prompt,
                "context": {"note": raw_context_value, "token": raw_secret},
                "filter_config_version": "../bad",
            },
        )
    finally:
        main_app.dependency_overrides.pop(get_db_session, None)

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 422
    assert raw_prompt not in encoded_body
    assert raw_context_value not in encoded_body
    assert raw_secret not in encoded_body
    assert "input" not in encoded_body
