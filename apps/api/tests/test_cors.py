import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_cors_origin_list_rejects_wildcard_with_credentials() -> None:
    settings = Settings(PROMPTGUARD_CORS_ORIGINS="*")

    with pytest.raises(ValueError):
        settings.cors_origin_list()


def test_cors_preflight_allows_configured_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_rejects_unconfigured_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
