import pytest
from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.executor import ParserPlanExecutor
from app.parser.fakes import FakeParserStepAdapter
from app.parser.models import (
    ParserAdapterCapability,
    ParserExecutionPlan,
    ParserFallbackRule,
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    sanitized_failure,
)
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration


def _payload():
    return ParserWorkerPayload(
        input_id="input-1", request_id="request-1", input_kind="text_wrapper",
        extraction_requirement="wrap_text", text="runtime text",
    )


def _step(step_id, ordinal, mode="always"):
    return ParserPlanStep(
        step_id=step_id, ordinal=ordinal, step_kind="wrap_text",
        capability_id=f"cap-{step_id}", execution_mode=mode,
    )


def _document():
    return ParsedDocument(
        input_id="input-1",
        blocks=[ParsedBlock(block_id="block-1", input_id="input-1", text="runtime result")],
    )


def _executor(adapter, capability_ids=("cap-one", "cap-two", "cap-primary", "cap-fallback")):
    registrations = tuple(
        ParserAdapterRegistration(
            ParserAdapterCapability(
                capability_id=capability_id,
                step_kinds=("wrap_text",),
            ),
            adapter,
        )
        for capability_id in capability_ids
    )
    return ParserPlanExecutor(InMemoryParserAdapterRegistry(registrations))


def test_parser_plan_executor_runs_steps_in_order():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="success"),
        "two": ParserStepResult(step_id="two", status="success", document=_document()),
    })
    plan = ParserExecutionPlan(
        plan_id="ordered", plan_kind="wrap_text", steps=(_step("one", 0), _step("two", 1))
    )
    result = _executor(adapter).execute(_payload(), None, plan)
    assert adapter.calls == ["one", "two"]
    assert result.parser_status == "parsed"


def test_parser_plan_executor_applies_fallback_rules_only_on_defined_triggers():
    adapter = FakeParserStepAdapter(results={
        "primary": ParserStepResult(step_id="primary", status="failed", trigger="adapter_unavailable", failure=sanitized_failure("OCR_ENGINE_UNAVAILABLE")),
        "fallback": ParserStepResult(step_id="fallback", status="success", document=_document()),
    })
    plan = ParserExecutionPlan(
        plan_id="fallback", plan_kind="image_ocr",
        steps=(_step("primary", 0), _step("fallback", 1, "fallback")),
        fallback_rules=(ParserFallbackRule(
            rule_id="rule", source_step_id="primary", trigger="adapter_unavailable",
            target_step_id="fallback", ordinal=0,
        ),),
    )
    result = _executor(adapter).execute(_payload(), None, plan)
    assert adapter.calls == ["primary", "fallback"]
    assert result.parser_status == "partial"


def test_undefined_trigger_does_not_apply_fallback():
    adapter = FakeParserStepAdapter(results={
        "primary": ParserStepResult(step_id="primary", status="failed", trigger="step_failed", failure=sanitized_failure("PARSER_WORKER_FAILED")),
    })
    plan = ParserExecutionPlan(
        plan_id="no-fallback", plan_kind="image_ocr",
        steps=(_step("primary", 0), _step("fallback", 1, "fallback")),
        fallback_rules=(ParserFallbackRule(
            rule_id="rule", source_step_id="primary", trigger="adapter_unavailable",
            target_step_id="fallback", ordinal=0,
        ),),
    )
    result = _executor(adapter).execute(_payload(), None, plan)
    assert adapter.calls == ["primary"]
    assert result.parser_status == "failed"


def test_primary_success_does_not_apply_fallback():
    adapter = FakeParserStepAdapter(results={
        "primary": ParserStepResult(step_id="primary", status="success", document=_document()),
    })
    plan = ParserExecutionPlan(
        plan_id="fallback-not-needed", plan_kind="image_ocr",
        steps=(_step("primary", 0), _step("fallback", 1, "fallback")),
        fallback_rules=(ParserFallbackRule(
            rule_id="rule", source_step_id="primary", trigger="step_failed",
            target_step_id="fallback", ordinal=0,
        ),),
    )

    result = _executor(adapter).execute(_payload(), None, plan)

    assert adapter.calls == ["primary"]
    assert result.parser_status == "parsed"


def test_failed_fallback_returns_sanitized_failure_without_running_other_steps():
    adapter = FakeParserStepAdapter(results={
        "primary": ParserStepResult(
            step_id="primary", status="failed", trigger="step_failed",
            failure=sanitized_failure("PARSER_WORKER_FAILED"),
        ),
        "fallback": ParserStepResult(
            step_id="fallback", status="failed", trigger="step_failed",
            failure=sanitized_failure("OCR_FAILED"),
        ),
    })
    plan = ParserExecutionPlan(
        plan_id="failed-fallback", plan_kind="image_ocr",
        steps=(
            _step("primary", 0),
            _step("fallback", 1, "fallback"),
            _step("after", 2),
        ),
        fallback_rules=(ParserFallbackRule(
            rule_id="rule", source_step_id="primary", trigger="step_failed",
            target_step_id="fallback", ordinal=0,
        ),),
    )

    result = _executor(adapter, capability_ids=("cap-primary", "cap-fallback", "cap-after")).execute(
        _payload(), None, plan
    )

    assert adapter.calls == ["primary", "fallback"]
    assert result.parser_status == "failed"
    assert result.failure.model_dump() == {
        "code": "OCR_FAILED",
        "message": "OCR_FAILED",
        "metadata": {"failure_code": "OCR_FAILED"},
    }


@pytest.mark.parametrize("plan_kind", ["metadata_only", "unsupported"])
def test_empty_non_execution_plan_does_not_resolve_an_adapter(plan_kind):
    adapter = FakeParserStepAdapter()
    result = _executor(adapter, capability_ids=()).execute(
        _payload(), None,
        ParserExecutionPlan(plan_id=plan_kind, plan_kind=plan_kind, steps=()),
    )

    assert adapter.calls == []
    assert result.document is None
    assert result.parser_status == "parsed"


def test_parser_plan_executor_preserves_failure_code():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="failed", trigger="step_failed", failure=sanitized_failure("PARSER_LIMIT_EXCEEDED")),
    })
    result = _executor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="fail", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.failure.code == "PARSER_LIMIT_EXCEEDED"


def test_fake_adapter_partial_result_is_preserved():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="partial", document=_document(), failure=sanitized_failure("PARSER_LIMIT_EXCEEDED")),
    })
    result = _executor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="partial", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.parser_status == "partial"
    assert result.document is not None


def test_raw_adapter_exception_is_sanitized():
    adapter = FakeParserStepAdapter(exception_message="PRIVATE_RAW_EXCEPTION C:\\private\\secret.pdf")
    result = _executor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="error", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.failure.code == "PARSER_WORKER_FAILED"
    assert "PRIVATE_RAW_EXCEPTION" not in result.failure.message


def test_executor_converts_missing_registry_adapter_to_private_structured_failure(caplog):
    payload = ParserWorkerPayload(
        input_id="input-private",
        request_id="request-private",
        input_kind="text_wrapper",
        extraction_requirement="wrap_text",
        text="PRIVATE_RAW_CONTENT",
    )
    plan = ParserExecutionPlan(
        plan_id="missing-adapter",
        plan_kind="wrap_text",
        steps=(_step("one", 0),),
    )

    result = _executor(FakeParserStepAdapter(), capability_ids=()).execute(payload, None, plan)

    assert result.parser_status == "failed"
    assert result.failure is not None
    assert result.failure.code == "UNSUPPORTED_FILE_KIND"
    exposed = result.failure.message + repr(result.failure.metadata) + caplog.text
    assert "PRIVATE_RAW_CONTENT" not in exposed
    assert "C:\\private\\secret.pdf" not in exposed
    assert "PRIVATE_RAW_EXCEPTION" not in exposed
