import pytest

from app.parser.models import (
    ParserAdapterCapability,
    ParserLicensePolicy,
    ParserPlanConfig,
    ParserPlanRequest,
    ParserWorkerPayload,
)
from app.parser.planning import ParserPlanResolver


def _payload(file_kind=None, requirement="native_parse", input_kind="file_reference"):
    values = {
        "input_id": "input-1",
        "request_id": "request-1",
        "input_kind": input_kind,
        "extraction_requirement": requirement,
        "file_kind": file_kind,
    }
    if input_kind == "text_wrapper":
        values["text"] = "representative text"
    else:
        values["file_ref"] = "opaque-ref"
        values["access_context"] = {
            "authenticated_subject_id": "subject-1",
            "session_id": "session-1",
            "request_id": "request-1",
        }
    return ParserWorkerPayload(**values)


def _capabilities():
    kinds = {
        "wrap_text", "native_text_extract", "pdf_native_text_extract", "pdf_coverage_evaluate",
        "render_ocr_candidate_pages", "ocr_primary", "ocr_fallback", "merge_blocks",
        "image_ocr", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse",
    }
    return tuple(
        ParserAdapterCapability(capability_id=f"cap-{kind}", step_kinds=(kind,), enabled=True)
        for kind in sorted(kinds)
    )


def _resolve(payload, capabilities=None, denied=()):
    return ParserPlanResolver().resolve_plan(
        ParserPlanRequest(
            payload=payload,
            config=ParserPlanConfig(),
            capabilities=_capabilities() if capabilities is None else capabilities,
            license_policy=ParserLicensePolicy(denied_capability_ids=denied),
        )
    )


@pytest.mark.parametrize(
    ("payload", "expected_kind"),
    [
        (_payload(requirement="wrap_text", input_kind="text_wrapper"), "wrap_text"),
        (_payload("plain_text"), "native_text"),
        (_payload("pdf", "native_parse_then_ocr_fallback"), "pdf_native_then_page_ocr"),
        (_payload("image", "ocr_required"), "image_ocr"),
        (_payload("office_document"), "office_parse"),
        (_payload("spreadsheet"), "spreadsheet_parse"),
        (_payload("slide"), "slide_parse"),
        (_payload("code"), "code_parse"),
        (_payload("unknown", "metadata_only"), "metadata_only"),
        (_payload("unknown", "unsupported"), "unsupported"),
    ],
)
def test_parser_plan_resolver_returns_typed_execution_plan(payload, expected_kind):
    resolution = _resolve(payload)
    assert resolution.failure is None
    assert resolution.plan is not None
    assert resolution.plan.plan_kind == expected_kind


def test_parser_execution_plan_steps_are_ordered_and_deterministic():
    payload = _payload("pdf", "native_parse_then_ocr_fallback")
    first = _resolve(payload).plan
    second = _resolve(payload).plan
    assert first == second
    assert [step.ordinal for step in first.steps] == list(range(len(first.steps)))


def test_parser_execution_plan_separates_steps_and_fallback_rules():
    plan = _resolve(_payload("pdf", "native_parse_then_ocr_fallback")).plan
    assert plan.steps
    assert plan.fallback_rules
    assert all(rule.target_step_id in {step.step_id for step in plan.steps} for rule in plan.fallback_rules)


def test_unsupported_and_metadata_only_are_distinct():
    metadata = _resolve(_payload("unknown", "metadata_only")).plan
    unsupported = _resolve(_payload("unknown", "unsupported")).plan
    assert metadata.plan_kind == "metadata_only"
    assert unsupported.plan_kind == "unsupported"
    assert metadata != unsupported


def test_unknown_file_kind_without_route_is_unsupported():
    assert _resolve(_payload("unknown")).plan.plan_kind == "unsupported"


def test_missing_adapter_capability_returns_registered_failure():
    resolution = _resolve(_payload("plain_text"), capabilities=())
    assert resolution.plan is None
    assert resolution.failure.code == "UNSUPPORTED_FILE_KIND"


def test_license_policy_block_returns_registered_failure():
    resolution = _resolve(_payload("plain_text"), denied=("cap-native_text_extract",))
    assert resolution.plan is None
    assert resolution.failure.code == "LICENSE_POLICY_VIOLATION"
