import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.tokens import create_access_token
from app.main import app as main_app
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session, require_active_user


class _FakeSession:
    def __init__(self, user):
        self.user = user

    async def get(self, model, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None


def _user(status: str = "ACTIVE"):
    return SimpleNamespace(id=uuid4(), role="USER", status=status)


def _bearer_header(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _client(user=None) -> TestClient:
    app = FastAPI()
    app.include_router(analyze_route.router)

    async def override_session():
        yield _FakeSession(user)

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def _override_client() -> TestClient:
    async def override_user():
        return _user()

    main_app.dependency_overrides[require_active_user] = override_user
    return TestClient(main_app)


def teardown_function() -> None:
    main_app.dependency_overrides.clear()


def analyze_payload(text: str) -> dict:
    return {
        "prompt": {
            "text": text,
            "input_method": "CLICK",
            "content_length": len(text),
        },
        "context": {
            "ai_service": "CHATGPT",
            "ai_service_domain": "chatgpt.com",
            "page_url_origin": "https://chatgpt.com",
            "extension_version": "0.1.0",
            "browser": "Chrome",
            "locale": "ko-KR",
        },
        "policy": {"version": "default:2026-05-30"},
        "client_request_id": "client-req-001",
    }


def test_analyze_requires_credentials() -> None:
    response = _client(_user()).post("/prompts/analyze", json=analyze_payload("hello"))

    assert response.status_code == 401


def test_analyze_rejects_disabled_user() -> None:
    user = _user(status="DISABLED")
    response = _client(user).post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=analyze_payload("hello"),
    )

    assert response.status_code == 403


def test_analyze_allows_prompt_without_detections() -> None:
    response = _override_client().post("/prompts/analyze", json=analyze_payload("일반적인 회의 안건을 정리해줘."))

    body = response.json()
    assert response.status_code == 200
    assert body["decision"]["action"] == "Allow"
    assert body["decision"]["risk_score"] == 1
    assert body["decision"]["risk_level"] == "LOW"
    assert body["decision"]["allow_original_send"] is True
    assert body["masked_prompt"] is None
    assert body["detections"] == []
    assert body["policy"] == {"version": "default:2026-05-30", "latest_version": "default:2026-05-30"}


def test_analyze_masks_email_and_phone_only_in_mask_response() -> None:
    raw_email = "member@example.com"
    raw_phone = "010-1234-5678"

    response = _override_client().post(
        "/prompts/analyze",
        json=analyze_payload(f"연락처는 {raw_email} / {raw_phone} 입니다."),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["decision"]["action"] == "Mask"
    assert body["decision"]["risk_level"] == "HIGH"
    assert body["decision"]["allow_original_send"] is False
    assert body["masked_prompt"] == "연락처는 [EMAIL_1] / [PHONE_1] 입니다."
    assert {item["type"] for item in body["detections"]} == {"EMAIL", "PHONE"}
    assert raw_email not in str(body["detections"])
    assert raw_phone not in str(body["detections"])


def test_analyze_blocks_rrn_without_returning_masked_prompt() -> None:
    raw_rrn = "900101-1234568"

    response = _override_client().post("/prompts/analyze", json=analyze_payload(f"주민등록번호 {raw_rrn} 확인"))

    body = response.json()
    assert response.status_code == 200
    assert body["decision"]["action"] == "Block"
    assert body["decision"]["risk_score"] == 90
    assert body["decision"]["risk_level"] == "CRITICAL"
    assert body["masked_prompt"] is None
    assert body["decision"]["allow_original_send"] is False
    assert body["detections"][0]["type"] == "RRN"
    assert raw_rrn not in str(body["detections"])


def test_analyze_response_does_not_echo_raw_prompt_or_detected_value() -> None:
    raw_email = "member@example.com"
    prompt = f"이 이메일 {raw_email}을 확인해줘."

    response = _override_client().post("/prompts/analyze", json=analyze_payload(prompt))

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 200
    assert prompt not in encoded_body
    assert raw_email not in json.dumps(response.json()["detections"], ensure_ascii=False)
    assert raw_email not in response.json()["decision"]["user_message"]
    assert raw_email not in response.json()["event_id"]


def test_main_app_registers_analyze_route_in_openapi() -> None:
    schema = main_app.openapi()

    assert "/prompts/analyze" in schema["paths"]
    assert "post" in schema["paths"]["/prompts/analyze"]


def test_main_app_validation_errors_do_not_echo_raw_prompt_or_context_values() -> None:
    raw_prompt = "SECRET-INVALID-PROMPT-DO-NOT-ECHO"
    raw_context_value = "private-context-value-do-not-echo"
    raw_secret = "ghp_seededsecret1234567890abcdef"
    payload = analyze_payload(raw_prompt)
    payload["prompt"]["content_length"] = 999
    payload["context"]["note"] = raw_context_value
    payload["context"]["token"] = raw_secret

    response = _override_client().post("/prompts/analyze", json=payload)

    encoded_body = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 422
    assert raw_prompt not in encoded_body
    assert raw_context_value not in encoded_body
    assert raw_secret not in encoded_body
    assert "input" not in encoded_body
