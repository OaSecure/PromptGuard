import pytest
from app.application.analyze.input_envelope import InputEnvelope
from app.application.analyze.parser_payload import build_parser_worker_payload
from app.domain.types.parser import FileMetadata
from app.parser.models import TempFileAccessContext


def test_composer_text_envelope_builds_text_wrapper_payload():
    payload = build_parser_worker_payload(
        _envelope(
            input_origin="composer_text",
            file_kind=None,
            extraction_requirement="wrap_text",
            text="representative composer text",
        ),
        access_context=None,
    )

    assert payload.input_kind == "text_wrapper"
    assert payload.extraction_requirement == "wrap_text"
    assert payload.text == "representative composer text"
    assert payload.file_ref is None
    assert payload.file_kind is None
    assert payload.access_context is None


def test_pdf_file_reference_envelope_builds_file_payload_with_access_context():
    access_context = TempFileAccessContext(
        authenticated_subject_id="subject_1",
        session_id="session_1",
        request_id="request_1",
        temp_scope_id="scope_1",
    )

    payload = build_parser_worker_payload(
        _envelope(
            input_origin="attached_file_ref",
            file_kind="pdf",
            extraction_requirement="native_parse_then_ocr_fallback",
            file_ref="fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
            metadata=FileMetadata(file_kind="pdf", size_bucket="small"),
        ),
        access_context=access_context,
    )

    assert payload.input_kind == "file_reference"
    assert payload.file_kind == "pdf"
    assert payload.file_ref == "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456"
    assert payload.extraction_requirement == "native_parse_then_ocr_fallback"
    assert payload.access_context == access_context
    assert payload.text is None


def test_image_file_reference_envelope_builds_ocr_required_payload():
    access_context = TempFileAccessContext(
        authenticated_subject_id="subject_1",
        session_id="session_1",
        request_id="request_1",
    )

    payload = build_parser_worker_payload(
        _envelope(
            input_origin="pasted_image_ref",
            file_kind="image",
            extraction_requirement="ocr_required",
            file_ref="fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
            metadata=FileMetadata(file_kind="image", size_bucket="tiny"),
        ),
        access_context=access_context,
    )

    assert payload.input_kind == "file_reference"
    assert payload.file_kind == "image"
    assert payload.extraction_requirement == "ocr_required"


@pytest.mark.parametrize("input_origin", ["attachment_metadata", "unsupported_attachment"])
def test_metadata_only_envelopes_do_not_create_parser_payload(input_origin):
    assert (
        build_parser_worker_payload(
            _envelope(
                input_origin=input_origin,
                file_kind="unknown",
                extraction_requirement="metadata_only",
                metadata=FileMetadata(file_kind="unknown", size_bucket="small"),
            ),
            access_context=None,
        )
        is None
    )


def test_file_reference_without_access_context_fails_before_worker_submission():
    with pytest.raises(ValueError, match="file_reference requires access_context"):
        build_parser_worker_payload(
            _envelope(
                input_origin="attached_file_ref",
                file_kind="plain_text",
                extraction_requirement="native_parse",
                file_ref="fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456",
                metadata=FileMetadata(file_kind="plain_text", size_bucket="tiny"),
            ),
            access_context=None,
        )


def _envelope(**overrides) -> InputEnvelope:
    values = {
        "input_id": "input_1",
        "request_id": "request_1",
        "input_origin": "composer_text",
        "file_kind": None,
        "extraction_requirement": "wrap_text",
        "file_ref": None,
        "text": None,
        "metadata": None,
    }
    values.update(overrides)
    return InputEnvelope(**values)
