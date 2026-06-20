from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)


class TextWrapperParserAdapter:
    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if (
            step.step_kind != "wrap_text"
            or payload.input_kind != "text_wrapper"
            or payload.text is None
            or resolved_file is not None
        ):
            return ParserStepResult(
                step_id=step.step_id,
                status="failed",
                trigger="step_failed",
                failure=sanitized_failure("UNSUPPORTED_FILE_KIND"),
            )

        blocks = []
        if payload.text:
            blocks.append(ParsedBlock(
                block_id="text-wrapper-0",
                input_id=payload.input_id,
                text=payload.text,
                source_type="text_wrapper",
            ))
        return ParserStepResult(
            step_id=step.step_id,
            status="success",
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=blocks,
                parser_id="text-wrapper-contract",
                parser_status="parsed",
                ocr_status="not_applicable",
            ),
        )
