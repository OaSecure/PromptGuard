import logging

from app.parser.executor import ParserPlanExecutor
from app.parser.fakes import FakeParserStepAdapter
from app.parser.models import ParserExecutionPlan, ParserPlanStep, ParserWorkerPayload


def test_parser_plan_failure_message_has_no_raw_content(caplog):
    sentinels = (
        "PRIVATE_RAW_TEXT", "PRIVATE_OCR_TEXT", "PRIVATE_EXTRACTED_TEXT",
        "confidential.pdf", "C:\\private\\confidential.pdf",
    )
    adapter = FakeParserStepAdapter(exception_message=" | ".join(sentinels))
    payload = ParserWorkerPayload(
        input_id="input-1", request_id="request-1", input_kind="text_wrapper",
        extraction_requirement="wrap_text", text="PRIVATE_RAW_TEXT",
    )
    plan = ParserExecutionPlan(
        plan_id="privacy", plan_kind="wrap_text",
        steps=(ParserPlanStep(
            step_id="one", ordinal=0, step_kind="wrap_text",
            capability_id="cap-wrap", execution_mode="always",
        ),),
    )
    with caplog.at_level(logging.ERROR):
        result = ParserPlanExecutor(adapter).execute(payload, None, plan)
    combined = result.failure.message + caplog.text + repr(plan.model_dump())
    assert all(value not in combined for value in sentinels)
