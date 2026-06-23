from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user


def test_file_reference_is_accepted_and_fails_closed_without_persistence():
    user = _user(); client, session = _client(user, rules=[])
    temp_scope_id = "tscope_abcdefghijklmnopqrstuvwxyz123456"
    item = {"input_id": "file_1", "kind": "file_reference", "source": "attached_file", "size_bytes": 42,
            "content_included": False, "file_ref": "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
            "temp_scope_id": temp_scope_id,
            "file_kind": "plain_text", "mime": "text/plain", "extension": "txt", "size_bucket": "tiny"}
    response = client.post("/prompts/analyze", headers=_bearer_header(user.id), json=_analyze_payload(item))
    assert response.status_code == 200
    body = response.json(); assert body["action"] == "Block" and body["input_results"][0]["content_scanned"] is False
    assert "file_ref" not in str(session.added) and "fref_" not in str(session.added)
    assert temp_scope_id not in str(session.added)
