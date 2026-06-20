import pytest
from pydantic import ValidationError

from app.application.analyze.input_envelope import InputEnvelope
from app.domain.types.common import OffsetMapping, TextRange
from app.domain.types.parser import FileMetadata, ParsedDocument
from app.domain.types.scanner import LexicalSignal


def test_text_range_accepts_empty_and_rejects_reversed_half_open_ranges():
    assert TextRange(start=3, end=3).model_dump() == {"start": 3, "end": 3}
    with pytest.raises(ValidationError): TextRange(start=3, end=2)
    with pytest.raises(ValidationError): OffsetMapping(normalized_start=2, normalized_end=1, original_start=0, original_end=1)


def test_file_document_requires_unknown_instead_of_none_for_unknown_file_kind():
    base = dict(input_id="in_file", file_ref="fr_synthetic_0001", parser_id="fake", parser_version="1", parser_status="parsed", ocr_status="not_applicable", blocks=[])
    with pytest.raises(ValidationError): ParsedDocument(file_kind=None, **base)
    assert ParsedDocument(file_kind="unknown", **base).file_kind == "unknown"


def test_lexical_signal_schema_has_no_raw_match_field():
    forbidden = {"raw_value", "matched_value", "secret_value", "text"}
    assert forbidden.isdisjoint(LexicalSignal.model_fields)


def test_input_envelope_enforces_text_and_file_reference_boundaries():
    text = InputEnvelope(input_id="in_text", request_id="req", input_origin="composer_text", file_kind=None,
                         extraction_requirement="wrap_text", text="synthetic text")
    assert text.file_ref is None
    metadata = FileMetadata(file_kind="unknown", size_bucket="small")
    file_input = InputEnvelope(input_id="in_file", request_id="req", input_origin="attached_file_ref", file_kind="unknown",
                               extraction_requirement="native_parse", file_ref="fr_synthetic_0001", metadata=metadata)
    assert file_input.text is None
    with pytest.raises(ValidationError):
        InputEnvelope(input_id="bad", request_id="req", input_origin="composer_text", file_kind=None,
                      extraction_requirement="wrap_text", text="x", file_ref="fr_synthetic_0001")
