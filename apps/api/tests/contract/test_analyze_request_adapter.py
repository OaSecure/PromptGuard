import pytest
from pydantic import ValidationError

from app.interfaces.http.analyze_request import ANALYZE_SCHEMA_VERSION, LegacyAnalyzeRequest, adapt_legacy_analyze_request


def context():
    return {"ai_service": "chatgpt", "ai_service_domain": "chatgpt.com", "page_url_origin": "https://chatgpt.com",
            "extension_version": "0.4.0", "browser": "chrome", "locale": "ko-KR"}


def text(input_id, content, source="composer"):
    return {"input_id": input_id, "kind": "text", "source": source, "size_bytes": len(content.encode()),
            "content_included": True, "content": content}


def request(*inputs, **extra):
    return LegacyAnalyzeRequest.model_validate({"client_request_id": "req_adapter", "filter_config_revision": "cfg_adapter",
                                                "context": context(), "inputs": list(inputs), **extra})


def test_maps_text_metadata_and_unsupported_inputs_in_order():
    metadata = {"input_id": "chip_1", "kind": "attachment_metadata", "source": "attachment_chip", "size_bytes": 10,
                "content_included": False, "metadata": {"extension": "pdf", "mime": "application/pdf"}}
    unsupported = {"input_id": "chip_2", "kind": "unsupported_attachment", "source": "attachment_chip", "size_bytes": 20,
                   "content_included": False, "content_unavailable_reason": "unsupported"}
    adapted = adapt_legacy_analyze_request(request(text("composer_1", "hello"), text("paste_1", "paste", "converted_paste"), metadata, unsupported), "trusted_login")
    assert adapted.v3_request.schema_version == ANALYZE_SCHEMA_VERSION == "v3"
    assert adapted.v3_request.login_id == "trusted_login"
    assert [item.input_id for item in adapted.v3_request.inputs] == ["composer_1", "paste_1", "chip_1", "chip_2"]
    assert adapted.v3_request.inputs[2].content_unavailable_reason == "metadata_only"
    assert adapted.legacy_view.client_request_id == "req_adapter"


def test_legacy_file_text_is_sidecar_only_and_never_a_v3_input():
    file_input = text("file_1", "legacy file text", "file")
    adapted = adapt_legacy_analyze_request(request(text("composer_1", "hello"), file_input), "trusted_login")
    assert [item.input_id for item in adapted.v3_request.inputs] == ["composer_1"]
    assert [item.input_id for item in adapted.legacy_file_text_sidecar] == ["file_1"]
    assert all(not (item.kind == "text" and item.source == "file") for item in adapted.v3_request.inputs)


@pytest.mark.parametrize("field", ["schema_version", "login_id", "file_ref", "prompt", "input", "file", "attachments", "raw_file_content", "base64_file_payload", "url", "local_path"])
def test_public_request_rejects_new_and_parallel_fields(field):
    with pytest.raises(ValidationError):
        LegacyAnalyzeRequest.model_validate({"client_request_id": "req", "filter_config_revision": "cfg", "context": context(),
                                             "inputs": [text("in_1", "hello")], field: "forbidden"})


def test_public_input_rejects_file_ref_and_duplicate_ids():
    with pytest.raises(ValidationError): request({**text("in_1", "hello"), "file_ref": "fr_synthetic"})
    with pytest.raises(ValidationError): request(text("in_1", "hello"), text("in_1", "again"))


def test_null_and_omitted_optional_fields_map_identically():
    omitted = adapt_legacy_analyze_request(request(text("a", "hello")), "login")
    explicit = adapt_legacy_analyze_request(request({**text("a", "hello"), "metadata": None, "content_unavailable_reason": None, "limit_exceeded": None}), "login")
    assert omitted.v3_request == explicit.v3_request
