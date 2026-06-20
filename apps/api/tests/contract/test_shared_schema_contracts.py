import pytest
from pydantic import ValidationError
from typing import get_args

from app.application.analyze.input_envelope import InputEnvelope
from app.domain.types.common import OffsetMapping, ParserPlanKind, ParserStepType, TextRange
from app.domain.types.parser import FileMetadata, ParsedDocument, ParserExecutionPlan, ParserFallbackRule, ParserLimits, ParserPlanStep, ParserWorkerPayload, TempFileAccessContext
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


def test_temp_access_context_uses_subject_and_scope_not_owner_id():
    assert "owner_id" not in TempFileAccessContext.model_fields
    context = TempFileAccessContext(authenticated_subject_id="subject_1", session_id="session_1", request_id="request_1", temp_scope_id="scope_1")
    assert context.authenticated_subject_id == "subject_1"


def test_parser_plan_literals_match_v35_contract():
    assert set(get_args(ParserPlanKind)) == {"wrap_text", "native_text", "pdf_native_then_page_ocr", "image_ocr", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse", "metadata_only", "unsupported"}
    assert set(get_args(ParserStepType)) == {"wrap_text", "native_text_extract", "pdf_native_text_extract", "pdf_coverage_evaluate", "render_ocr_candidate_pages", "ocr_primary", "ocr_fallback", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse", "merge_blocks", "metadata_only", "unsupported"}


def test_parser_execution_plan_preserves_order_and_separates_fallbacks():
    steps = [ParserPlanStep(step_id="step_1", ordinal=0, step_type="pdf_native_text_extract"), ParserPlanStep(step_id="step_2", ordinal=1, step_type="pdf_coverage_evaluate", on_failure="apply_fallback")]
    fallback = ParserFallbackRule(rule_id="fallback_1", trigger="coverage_low", fallback_action="run_step", fallback_target="step_ocr", failure_code="PDF_LOW_COVERAGE")
    plan = ParserExecutionPlan(plan_id="plan_1", plan_kind="pdf_native_then_page_ocr", input_id="in_1", steps=steps, fallback_rules=[fallback])
    assert [step.ordinal for step in plan.steps] == [0, 1]
    assert plan.fallback_rules == [fallback]
    with pytest.raises(ValidationError):
        ParserExecutionPlan(plan_id="bad", plan_kind="native_text", input_id="in_1", steps=list(reversed(steps)))


def test_parser_worker_payload_is_coarse_and_contains_no_execution_plan():
    assert "execution_plan" not in ParserWorkerPayload.model_fields
    assert "extraction_requirement" in ParserWorkerPayload.model_fields
    payload = ParserWorkerPayload(request_id="req_1", input_id="in_1", input_origin="attached_file_ref", file_kind="unknown",
                                  extraction_requirement="native_parse", file_ref="fr_synthetic_0001", text=None,
                                  metadata=FileMetadata(file_kind="unknown", size_bucket="small"),
                                  parser_limits=ParserLimits(max_bytes=1024, timeout_ms=1000, max_pages=10),
                                  access_context=TempFileAccessContext(authenticated_subject_id="subject_1", session_id="session_1", request_id="req_1"))
    assert payload.extraction_requirement == "native_parse"
