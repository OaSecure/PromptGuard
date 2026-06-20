from app.atoms.models import ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort


OFFICE_STEPS = {
    "office_document": "office_parse",
    "spreadsheet": "spreadsheet_parse",
    "slide": "slide_parse",
}


class OfficeParserFoundationAdapter:
    def __init__(self, content_source: ResolvedFileContentSourcePort) -> None:
        self._content_source = content_source

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        expected_step = OFFICE_STEPS.get(payload.file_kind or "")
        if expected_step is None or step.step_kind != expected_step:
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")
        if resolved_file is None or resolved_file.file_kind != payload.file_kind:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        try:
            content = self._content_source.read(resolved_file)
        except Exception:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        if not content:
            return self._result(step.step_id, payload, "success", "parsed")
        if not content.startswith(b"PK"):
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")
        return self._result(
            step.step_id,
            payload,
            "partial",
            "partial",
            "PARSER_NOT_IMPLEMENTED",
        )

    @staticmethod
    def _result(
        step_id: str,
        payload: ParserWorkerPayload,
        status: str,
        parser_status: str,
        failure_code: str | None = None,
    ) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status=status,
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=[],
                file_ref=payload.file_ref,
                file_type=payload.file_kind,
                parser_id="office-foundation",
                parser_status=parser_status,
                ocr_status="not_applicable",
            ),
            failure=sanitized_failure(failure_code) if failure_code else None,
        )

    @staticmethod
    def _failure(step_id: str, code: str) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status="failed",
            trigger="step_failed",
            failure=sanitized_failure(code),
        )
