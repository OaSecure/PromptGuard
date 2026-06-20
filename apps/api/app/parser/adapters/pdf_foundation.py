from app.atoms.models import ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort


class PdfParserFoundationAdapter:
    def __init__(self, content_source: ResolvedFileContentSourcePort) -> None:
        self._content_source = content_source

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if step.step_kind != "pdf_native_text_extract" or payload.file_kind != "pdf":
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")
        if resolved_file is None or resolved_file.file_kind != "pdf":
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        try:
            content = self._content_source.read(resolved_file)
        except Exception:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        if not content:
            return self._result(step.step_id, payload, "success", "parsed")
        if not content.startswith(b"%PDF-"):
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
                file_type="pdf",
                parser_id="pdf-foundation",
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
