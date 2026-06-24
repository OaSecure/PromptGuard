from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_dashboard_root_redirects_to_trailing_slash() -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard/index.html")


def test_site_root_redirects_to_landing_page() -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard/index.html")


def test_dashboard_entry_redirects_to_landing_page() -> None:
    response = client.get("/dashboard/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard/index.html")


def test_dashboard_html_pages_are_served_under_dashboard_prefix() -> None:
    expected_markers = {
        "admin.html": "대시보드 열기",
        "event-detail.html": "./static/event-detail.js",
        "events.html": "./static/events.js",
        "filters.html": "./static/filters.js",
        "index.html": "OASECURE SOLUTION",
        "login.html": "./static/login.js",
        "overview.html": "./static/overview.js",
        "status.html": "./static/status.js",
        "users.html": "./static/users.js",
    }

    for page, marker in expected_markers.items():
        response = client.get(f"/dashboard/{page}")

        assert response.status_code == 200, page
        assert "text/html" in response.headers["content-type"], page
        assert marker in response.text, page


def test_dashboard_extensionless_page_paths_do_not_shadow_api_routes() -> None:
    api_routes = {
        "/dashboard/status": 401,
        "/dashboard/overview": 401,
        "/dashboard/events": 401,
        "/dashboard/filters": 401,
        "/dashboard/users": 401,
    }

    for path, expected_status in api_routes.items():
        response = client.get(path)

        assert response.status_code == expected_status, path
        assert response.headers["content-type"].startswith("application/json"), path


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
