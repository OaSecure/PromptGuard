import logging

from app.atoms.models import ParsedDocument
from app.parser.models import (
    FileParserResult,
    OcrStatus,
    ParserBoundaryError,
    ParserExecutionPlan,
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ParserAdapterRegistryPort

logger = logging.getLogger(__name__)


class ParserPlanExecutor:
    def __init__(self, registry: ParserAdapterRegistryPort) -> None:
        self._registry = registry

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
                result = self._execute_step(step, payload, resolved_file)
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
                fallback_result = self._execute_step(
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
                ocr_status=_document_ocr_status(document),
                failure=last_failure if partial else None,
            )
        except ParserBoundaryError as error:
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=error.failure,
            )
        except Exception:
            logger.error("Parser plan step failed", extra={"failure_code": "PARSER_WORKER_FAILED"})
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=sanitized_failure("PARSER_WORKER_FAILED"),
            )

    def _execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        adapter = self._registry.resolve_adapter(step.capability_id, step.step_kind)
        return adapter.execute_step(step, payload, resolved_file)


def _document_ocr_status(document: ParsedDocument | None) -> OcrStatus:
    if document is None:
        return "not_applicable"
    return _result_ocr_status(document.ocr_status)


def _result_ocr_status(value: str | None) -> OcrStatus:
    if value == "text_found":
        return "text_found"
    if value == "no_text_detected":
        return "no_text_detected"
    if value == "timeout":
        return "timeout"
    if value == "failed":
        return "failed"
    return "not_applicable"
