import logging

from app.parser.models import (
    FileParserResult,
    ParserExecutionPlan,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ParserStepAdapterPort

logger = logging.getLogger(__name__)


class ParserPlanExecutor:
    def __init__(self, adapter: ParserStepAdapterPort) -> None:
        self._adapter = adapter

    def execute(
        self,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
        plan: ParserExecutionPlan,
    ) -> FileParserResult:
        document = None
        last_failure = None
        partial = False
        steps_by_id = {step.step_id: step for step in plan.steps}
        try:
            for step in plan.steps:
                if step.execution_mode == "fallback":
                    continue
                result = self._adapter.execute_step(step, payload, resolved_file)
                document = result.document or document
                last_failure = result.failure or last_failure
                partial = partial or result.status == "partial"
                if result.status != "failed":
                    continue
                rule = next((
                    rule for rule in plan.fallback_rules
                    if rule.source_step_id == step.step_id and rule.trigger == result.trigger
                ), None)
                if rule is None:
                    return FileParserResult(
                        input_id=payload.input_id, document=document, parser_status="failed",
                        failure=result.failure or sanitized_failure("PARSER_WORKER_FAILED"),
                    )
                fallback_result = self._adapter.execute_step(
                    steps_by_id[rule.target_step_id], payload, resolved_file
                )
                document = fallback_result.document or document
                last_failure = fallback_result.failure or last_failure
                partial = True
                if fallback_result.status == "failed":
                    return FileParserResult(
                        input_id=payload.input_id, document=document, parser_status="failed",
                        failure=fallback_result.failure or sanitized_failure("PARSER_WORKER_FAILED"),
                    )
            return FileParserResult(
                input_id=payload.input_id,
                document=document,
                parser_status="partial" if partial else "parsed",
                failure=last_failure if partial else None,
            )
        except Exception:
            logger.error("Parser plan step failed", extra={"failure_code": "PARSER_WORKER_FAILED"})
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=sanitized_failure("PARSER_WORKER_FAILED"),
            )
