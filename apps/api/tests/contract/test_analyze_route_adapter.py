from app.interfaces.http.analyze_request import adapt_legacy_analyze_request as real_adapter
from app.routes import analyze as analyze_route
from tests.test_analyze import _analyze_payload, _bearer_header, _client, _text_input, _user


def test_route_calls_adapter_with_trusted_authenticated_login(monkeypatch):
    user = _user()
    captured = []

    def spy(request, authenticated_login_id):
        captured.append((request, authenticated_login_id))
        return real_adapter(request, authenticated_login_id)

    monkeypatch.setattr(analyze_route, "adapt_legacy_analyze_request", spy)
    client, _ = _client(user, rules=[])
    response = client.post("/prompts/analyze", headers=_bearer_header(user.id), json=_analyze_payload(_text_input("in_1", "hello")))
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0][1] == user.login_id


def test_existing_attachment_metadata_remains_accepted():
    user = _user()
    client, _ = _client(user, rules=[])
    item = {"input_id": "chip_1", "kind": "attachment_metadata", "source": "attachment_chip", "size_bytes": 10,
            "content_included": False, "metadata": {"extension": "pdf", "mime": "application/pdf"}}
    response = client.post("/prompts/analyze", headers=_bearer_header(user.id), json=_analyze_payload(item))
    assert response.status_code == 200


def test_route_rejects_legacy_file_text_input_before_analysis():
    user = _user()
    client, fake_session = _client(user, rules=[])

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(_text_input("file_1", "legacy file text", source="file")),
    )

    assert response.status_code == 422
    assert fake_session.added == []
    encoded = response.text
    assert "legacy file text" not in encoded
