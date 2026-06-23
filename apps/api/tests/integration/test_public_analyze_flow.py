import json

import pytest
from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import FileParserResult
from app.routes import analyze as analyze_route

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
    temp_scope_id = "tscope_abcdefghijklmnopqrstuvwxyz123456"
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": opaque_ref,
        "temp_scope_id": temp_scope_id,
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
    assert temp_scope_id not in persisted
    assert "size_bytes" not in persisted
    assert "masked_prompt" not in persisted


def test_file_reference_routes_through_parser_worker_without_persisting_runtime_text():
    user = _user()
    client, session = _client(user, rules=[])
    opaque_ref = "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456"
    temp_scope_id = "tscope_abcdefghijklmnopqrstuvwxyz123456"
    runtime_text = "runtime parsed admin@example.com"
    parser_pool = _FakeParserWorkerPool(runtime_text)
    client.app.dependency_overrides[analyze_route.get_parser_worker_pool] = lambda: parser_pool
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": opaque_ref,
        "temp_scope_id": temp_scope_id,
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

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["input_results"][0]["content_scanned"] is True
    assert body["detections"][0]["kind"] == "file_reference"
    assert parser_pool.payloads[0].file_ref == opaque_ref
    assert parser_pool.payloads[0].access_context.temp_scope_id == temp_scope_id
    encoded_body = json.dumps(body, ensure_ascii=False)
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    assert runtime_text not in encoded_body
    assert runtime_text not in persisted
    assert opaque_ref not in persisted
    assert temp_scope_id not in persisted


class _FakeParserWorkerPool:
    def __init__(self, text: str) -> None:
        self.text = text
        self.payloads = []

    def execute(self, payload, timeout_ms):
        self.payloads.append(payload)
        return FileParserResult(
            input_id=payload.input_id,
            parser_status="parsed",
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=[ParsedBlock(block_id="block_1", input_id=payload.input_id, text=self.text)],
            ),
        )
