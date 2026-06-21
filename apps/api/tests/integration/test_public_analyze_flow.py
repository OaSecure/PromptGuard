import json

import pytest

from tests.contract.current_behavior.test_analyze_golden import (
    post_snapshot,
    rule,
    text,
)
from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user


def _stable(value):
    value = json.loads(json.dumps(value, default=str))
    value.get("response", {}).pop("checked_at", None)
    value.get("response", {}).pop("event_id", None)
    return value


@pytest.mark.parametrize(
    ("action", "expected"),
    [("ALLOW", "Allow"), ("WARN", "Warn"), ("MASK", "Mask"), ("BLOCK", "Block")],
)
def test_public_analyze_actions_are_deterministic_and_storage_is_private(action, expected):
    rules = [] if action == "ALLOW" else [rule(action)]
    content = "ordinary deterministic note" if action == "ALLOW" else "snapshot marker"

    first = post_snapshot(rules, [text("input_1", content)])
    second = post_snapshot(rules, [text("input_1", content)])

    assert _stable(first) == _stable(second)
    assert first["response"]["action"] == expected
    serialized_storage = json.dumps(first["storage"], default=str)
    assert content not in serialized_storage
    assert "masked_prompt" not in serialized_storage


def test_converted_paste_mask_fails_closed_without_persisting_masked_prompt():
    actual = post_snapshot(
        [rule("MASK")],
        [text("paste_1", "snapshot marker", source="converted_paste")],
    )

    assert actual["response"]["action"] == "Block"
    assert "masked_prompt" not in actual["response"]
    assert "masked_prompt" not in json.dumps(actual["storage"], default=str)


def test_file_reference_http_boundary_fails_closed_without_persisting_reference():
    user = _user()
    client, session = _client(user, rules=[])
    opaque_ref = "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456"
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": opaque_ref,
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "Block"
    assert response.json()["input_results"][0]["content_scanned"] is False
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str)
    assert opaque_ref not in persisted
    assert "size_bytes" not in persisted
    assert "masked_prompt" not in persisted
