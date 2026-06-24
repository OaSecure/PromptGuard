from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routes import extension_config
from app.routes.auth import require_active_user


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
    assert body["policy_version"] == "cfg_default"
    assert body["timeout_ms"] == 8000
    assert body["ai_service_configs"][0]["service"] == "CHATGPT"
    assert body["ai_service_configs"][0]["selectors"]["input"]
    assert body["file_upload"]["enabled"] is True
    assert body["file_upload"]["max_file_size_bytes"] == 1_048_576
    assert ".pdf" in body["file_upload"]["excluded_extensions"]
    assert "raw_prompt" not in response.text
    assert "original_filename" not in response.text


def test_extension_config_accepts_active_admin() -> None:
    client = _client_with_user(_user("ADMIN"))

    response = client.get("/config/extension")

    assert response.status_code == 200
