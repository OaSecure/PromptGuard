from types import SimpleNamespace

from app.core.config import Settings
from app.routes import extension_config
from app.routes.auth import require_active_user
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client_with_user(user=None) -> TestClient:
    app = FastAPI()
    app.include_router(extension_config.router)

    if user is not None:
        async def override_current_user():
            return user

        app.dependency_overrides[require_active_user] = override_current_user

    app.dependency_overrides[extension_config.get_settings] = lambda: Settings(
        PROMPTGUARD_API_PUBLIC_URL="http://localhost:8000",
        PROMPTGUARD_TEMP_FILE_MAX_BYTES=1_048_576,
        PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS=120_000,
    )
    return TestClient(app)


def _user(role: str):
    return SimpleNamespace(role=role, status="ACTIVE", login_id=role.lower())


def test_extension_config_requires_bearer_user() -> None:
    client = _client_with_user()

    response = client.get("/config/extension")

    assert response.status_code == 401


def test_extension_config_accepts_active_user_and_returns_extension_shape() -> None:
    client = _client_with_user(_user("USER"))

    response = client.get("/config/extension")

    assert response.status_code == 200
    body = response.json()
    assert body["api_base_url"] == "http://localhost:8000"
    assert body["filter_config_revision"] == "cfg_default"
    assert body["request_timeouts"] == {"config_request_ms": 5000, "analyze_request_ms": 120_000}
    assert body["input_limits"] == {
        "composer_text_bytes": 262_144,
        "converted_paste_text_bytes": 1_048_576,
        "file_text_scan_bytes": 1_048_576,
        "analyze_request_bytes": 2_097_152,
    }
    assert body["policy_version"] == "cfg_default"
    assert body["timeout_ms"] == 120_000
    assert body["ai_service_configs"][0]["service"] == "CHATGPT"
    assert body["ai_service_configs"][0]["selectors"]["input"]
    assert body["file_upload"]["enabled"] is True
    assert body["attachment_policy"]["enabled"] is True
    assert body["attachment_policy"] == body["file_upload"]
    assert body["file_upload"]["max_file_size_bytes"] == 1_048_576
    assert ".pdf" in body["file_upload"]["allowed_extensions"]
    assert ".png" in body["file_upload"]["allowed_extensions"]
    assert ".pdf" not in body["file_upload"]["excluded_extensions"]
    assert "raw_prompt" not in response.text
    assert "original_filename" not in response.text


def test_extension_config_accepts_active_admin() -> None:
    client = _client_with_user(_user("ADMIN"))

    response = client.get("/config/extension")

    assert response.status_code == 200
