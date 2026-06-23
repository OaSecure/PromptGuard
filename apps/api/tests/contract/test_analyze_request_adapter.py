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
    assert adapted.v3_request.schema_version == ANALYZE_SCHEMA_VERSION
    assert adapted.v3_request.login_id == "trusted_login"
    assert [item.input_id for item in adapted.v3_request.inputs] == ["composer_1", "paste_1", "chip_1", "chip_2"]
    assert adapted.v3_request.inputs[2].content_unavailable_reason == "metadata_only"
    assert adapted.legacy_view.client_request_id == "req_adapter"


def test_legacy_file_text_is_not_accepted_as_public_input():
    file_input = text("file_1", "legacy file text", "file")
    with pytest.raises(ValidationError):
        request(text("composer_1", "hello"), file_input)


@pytest.mark.parametrize("field", ["schema_version", "login_id", "file_ref", "prompt", "input", "file", "attachments", "raw_file_content", "base64_file_payload", "url", "local_path"])
def test_public_request_rejects_new_and_parallel_fields(field):
    with pytest.raises(ValidationError):
        LegacyAnalyzeRequest.model_validate({"client_request_id": "req", "filter_config_revision": "cfg", "context": context(),
                                             "inputs": [text("in_1", "hello")], field: "forbidden"})


def test_public_input_rejects_file_ref_and_duplicate_ids():
    with pytest.raises(ValidationError): request({**text("in_1", "hello"), "file_ref": "fr_synthetic"})
    with pytest.raises(ValidationError): request(text("in_1", "hello"), text("in_1", "again"))


def test_file_reference_requires_temp_scope_id_and_adapts_it():
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
        "temp_scope_id": "tscope_abcdefghijklmnopqrstuvwxyz123456",
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    adapted = adapt_legacy_analyze_request(request(item), "trusted_login")

    assert adapted.v3_request.inputs[0].file_ref == item["file_ref"]
    assert adapted.v3_request.inputs[0].temp_scope_id == item["temp_scope_id"]


def test_file_reference_without_temp_scope_id_is_rejected():
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    with pytest.raises(ValidationError):
        request(item)


def test_pr0_supported_attachment_metadata_remains_accepted():
    metadata = {"extension": "pdf", "mime": "application/pdf", "size_bytes": 42,
                "attachment_kind": "file", "attachment_index": 0}
    item = {"input_id": "chip_1", "kind": "attachment_metadata", "source": "attachment_chip", "size_bytes": 42,
            "content_included": False, "metadata": metadata}
    assert request(item).inputs[0].metadata == metadata


@pytest.mark.parametrize("key", ["name", "filename", "file_name", "original_filename", "path", "url"])
def test_pr0_forbidden_attachment_identity_and_location_metadata_stays_rejected(key):
    item = {"input_id": "chip_1", "kind": "attachment_metadata", "source": "attachment_chip", "size_bytes": 42,
            "content_included": False, "metadata": {key: "forbidden-value"}}
    with pytest.raises(ValidationError): request(item)


def test_null_and_omitted_optional_fields_map_identically():
    omitted = adapt_legacy_analyze_request(request(text("a", "hello")), "login")
    explicit = adapt_legacy_analyze_request(request({**text("a", "hello"), "metadata": None, "content_unavailable_reason": None, "limit_exceeded": None}), "login")
    assert omitted.v3_request == explicit.v3_request
