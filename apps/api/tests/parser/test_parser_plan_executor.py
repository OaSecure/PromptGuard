from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.executor import ParserPlanExecutor
from app.parser.fakes import FakeParserStepAdapter
from app.parser.models import (
    ParserExecutionPlan,
    ParserFallbackRule,
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    sanitized_failure,
)


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


def test_parser_plan_executor_runs_steps_in_order():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="success"),
        "two": ParserStepResult(step_id="two", status="success", document=_document()),
    })
    plan = ParserExecutionPlan(
        plan_id="ordered", plan_kind="wrap_text", steps=(_step("one", 0), _step("two", 1))
    )
    result = ParserPlanExecutor(adapter).execute(_payload(), None, plan)
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
    result = ParserPlanExecutor(adapter).execute(_payload(), None, plan)
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
    result = ParserPlanExecutor(adapter).execute(_payload(), None, plan)
    assert adapter.calls == ["primary"]
    assert result.parser_status == "failed"


def test_parser_plan_executor_preserves_failure_code():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="failed", trigger="step_failed", failure=sanitized_failure("PARSER_LIMIT_EXCEEDED")),
    })
    result = ParserPlanExecutor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="fail", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.failure.code == "PARSER_LIMIT_EXCEEDED"


def test_fake_adapter_partial_result_is_preserved():
    adapter = FakeParserStepAdapter(results={
        "one": ParserStepResult(step_id="one", status="partial", document=_document(), failure=sanitized_failure("PARSER_LIMIT_EXCEEDED")),
    })
    result = ParserPlanExecutor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="partial", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.parser_status == "partial"
    assert result.document is not None


def test_raw_adapter_exception_is_sanitized():
    adapter = FakeParserStepAdapter(exception_message="PRIVATE_RAW_EXCEPTION C:\\private\\secret.pdf")
    result = ParserPlanExecutor(adapter).execute(
        _payload(), None, ParserExecutionPlan(plan_id="error", plan_kind="wrap_text", steps=(_step("one", 0),))
    )
    assert result.failure.code == "PARSER_WORKER_FAILED"
    assert "PRIVATE_RAW_EXCEPTION" not in result.failure.message
