from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_dashboard_root_redirects_to_trailing_slash() -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard/")


def test_dashboard_entry_serves_status_shell_from_same_api_server() -> None:
    response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<div id="status-app"></div>' in response.text
    assert './static/status.js' in response.text


def test_dashboard_static_assets_are_served_under_dashboard_prefix() -> None:
    response = client.get("/dashboard/static/main.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "dashboard" in response.text


def test_dashboard_public_assets_are_served_under_dashboard_prefix() -> None:
    response = client.get("/dashboard/public/images/logo.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_dashboard_static_serving_does_not_shadow_status_api() -> None:
    response = client.get("/dashboard/status")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


def test_dashboard_unknown_static_page_returns_404_without_filesystem_path() -> None:
    response = client.get("/dashboard/not-a-dashboard-page")

    assert response.status_code == 404
    assert "apps" not in response.text.lower()
    assert "promptguard_publish" not in response.text.lower()
