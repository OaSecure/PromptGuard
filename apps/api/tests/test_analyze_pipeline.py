from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.routes.auth import require_active_user


def active_user():
    return SimpleNamespace(id=uuid4(), role="USER", status="ACTIVE")


def analyze_payload(text: str) -> dict:
    return {
        "prompt": {
            "text": text,
            "input_method": "textarea",
            "content_length": len(text),
        },
        "context": {
            "ai_service": "ChatGPT",
            "ai_service_domain": "chatgpt.com",
            "page_url_origin": "https://chatgpt.com",
            "extension_version": "0.1.0",
            "browser": "Chrome",
            "locale": "ko-KR",
        },
        "filter_config_version": "default-v1",
        "client_request_id": "client-req-001",
    }


def build_client() -> TestClient:
    async def override_user():
        return active_user()

    app.dependency_overrides[require_active_user] = override_user
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_analyze_allows_prompt_without_detections() -> None:
    client = build_client()

    response = client.post("/prompts/analyze", json=analyze_payload("일반적인 회의 안건을 정리해줘."))

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Allow"
    assert body["risk_score"] == 0
    assert body["risk_level"] == "low"
    assert body["allow_original_send"] is True
    assert body["masked_prompt"] is None
    assert body["detections"] == []


def test_analyze_masks_email_and_phone_only_in_mask_response() -> None:
    raw_email = "member@example.com"
    raw_phone = "010-1234-5678"
    client = build_client()

    response = client.post("/prompts/analyze", json=analyze_payload(f"연락처는 {raw_email} / {raw_phone} 입니다."))

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Mask"
    assert body["risk_level"] == "high"
    assert body["allow_original_send"] is False
    assert body["masked_prompt"] == "연락처는 [EMAIL_1] / [PHONE_1] 입니다."
    assert {item["detector_key"] for item in body["detections"]} == {"EMAIL", "PHONE"}
    assert raw_email not in str(body["detections"])
    assert raw_phone not in str(body["detections"])


def test_analyze_blocks_rrn_without_returning_masked_prompt() -> None:
    raw_rrn = "900101-1234568"
    client = build_client()

    response = client.post("/prompts/analyze", json=analyze_payload(f"주민등록번호 {raw_rrn} 확인"))

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["risk_score"] == 90
    assert body["risk_level"] == "critical"
    assert body["masked_prompt"] is None
    assert body["allow_original_send"] is False
    assert body["detections"][0]["detector_key"] == "RRN"
    assert raw_rrn not in str(body["detections"])


def test_analyze_response_does_not_echo_raw_prompt_or_detected_value() -> None:
    raw_email = "member@example.com"
    prompt = f"이 이메일 {raw_email}을 확인해줘."
    client = build_client()

    response = client.post("/prompts/analyze", json=analyze_payload(prompt))

    body = response.json()
    assert response.status_code == 200
    assert prompt not in str(body["detections"])
    assert raw_email not in str(body["detections"])
    assert raw_email not in body["user_message"]
    assert raw_email not in body["event_id"]


def test_analyze_validation_error_does_not_echo_raw_prompt() -> None:
    raw_prompt = "member@example.com"
    client = build_client()
    payload = analyze_payload(raw_prompt)
    payload["prompt"]["content_length"] = 999

    response = client.post("/prompts/analyze", json=payload)

    assert response.status_code == 422
    assert raw_prompt not in response.text
