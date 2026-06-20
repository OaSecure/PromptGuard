from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort


class NativeTextAdapter:
    def __init__(self, content_source: ResolvedFileContentSourcePort) -> None:
        self._content_source = content_source

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if (
            step.step_kind != "native_text_extract"
            or payload.file_kind != "plain_text"
            or resolved_file is None
            or resolved_file.file_kind != "plain_text"
        ):
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")

        try:
            content = self._content_source.read(resolved_file)
        except Exception:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return self._failure(step.step_id, "TEXT_DECODE_FAILED")

        blocks = []
        if text:
            blocks.append(ParsedBlock(
                block_id="native-text-0",
                input_id=payload.input_id,
                text=text,
                source_type="text",
            ))
        return ParserStepResult(
            step_id=step.step_id,
            status="success",
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=blocks,
                file_ref=payload.file_ref,
                file_type="plain_text",
                parser_id="native-text-contract",
                parser_status="parsed",
            ),
        )

    @staticmethod
    def _failure(step_id: str, code: str) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status="failed",
            trigger="step_failed",
            failure=sanitized_failure(code),
        )
