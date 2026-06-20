from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort


class CodeTextParserAdapter:
    def __init__(self, content_source: ResolvedFileContentSourcePort) -> None:
        self._content_source = content_source

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if (
            step.step_kind != "code_parse"
            or payload.file_kind != "code"
            or resolved_file is None
            or resolved_file.file_kind != "code"
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
                block_id="code-text-0",
                input_id=payload.input_id,
                text=text,
                source_type="code_block",
                location={
                    "kind": "code",
                    "line_start": 1,
                    "line_end": max(1, len(text.splitlines())),
                },
            ))
        return ParserStepResult(
            step_id=step.step_id,
            status="success",
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=blocks,
                file_ref=payload.file_ref,
                file_type="code",
                parser_id="code-text-contract",
                parser_status="parsed",
                ocr_status="not_applicable",
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
