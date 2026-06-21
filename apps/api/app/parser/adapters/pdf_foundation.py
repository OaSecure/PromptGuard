import io
from collections.abc import Callable
from typing import Any

from pypdf import PdfReader

from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.pdf_coverage import PdfPageCoverageInput, count_meaningful_characters
from app.parser.ports import ResolvedFileContentSourcePort


class PdfParserFoundationAdapter:
    def __init__(
        self,
        content_source: ResolvedFileContentSourcePort,
        reader_factory: Callable[[io.BytesIO], Any] | None = None,
    ) -> None:
        self._content_source = content_source
        self._reader_factory = reader_factory or PdfReader

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
            return self._result(step.step_id, payload, "success", "parsed", [], {})
        if not content.startswith(b"%PDF-"):
            return self._failure(step.step_id, "PDF_PARSE_FAILED")

        try:
            reader = self._reader_factory(io.BytesIO(content))
            if reader.is_encrypted:
                return self._failure(step.step_id, "PDF_ENCRYPTED")
            pages = reader.pages
        except Exception:
            return self._failure(step.step_id, "PDF_PARSE_FAILED")

        blocks: list[ParsedBlock] = []
        coverage_inputs: list[PdfPageCoverageInput] = []
        failed_page_indices: list[int] = []
        for page_index, page in enumerate(pages, start=1):
            image_evidence = _image_evidence(page)
            try:
                text = page.extract_text() or ""
            except Exception:
                failed_page_indices.append(page_index)
                coverage_inputs.append(PdfPageCoverageInput(
                    page_index=page_index,
                    native_extraction_status="failed",
                    meaningful_character_count=0,
                    image_evidence="unknown",
                ))
                continue
            if text:
                blocks.append(ParsedBlock(
                    block_id=f"pdf-page-{page_index}",
                    input_id=payload.input_id,
                    text=text,
                    source_type="pdf_native_page",
                    location={"kind": "pdf", "page": page_index},
                ))
            coverage_inputs.append(PdfPageCoverageInput(
                page_index=page_index,
                native_extraction_status="success",
                meaningful_character_count=count_meaningful_characters(text),
                image_evidence=image_evidence,
            ))

        metadata: dict[str, Any] = {
            "page_coverage_inputs": [item.model_dump() for item in coverage_inputs]
        }
        if failed_page_indices:
            metadata["failed_page_indices"] = failed_page_indices
            return self._result(
                step.step_id,
                payload,
                "partial",
                "partial",
                blocks,
                metadata,
                "PDF_PAGE_EXTRACTION_PARTIAL",
            )
        return self._result(step.step_id, payload, "success", "parsed", blocks, metadata)

    @staticmethod
    def _result(
        step_id: str,
        payload: ParserWorkerPayload,
        status: str,
        parser_status: str,
        blocks: list[ParsedBlock],
        metadata: dict[str, Any],
        failure_code: str | None = None,
    ) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status=status,
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=blocks,
                file_ref=payload.file_ref,
                file_type="pdf",
                parser_id="pdf-native-pypdf",
                parser_status=parser_status,
                ocr_status="not_applicable",
                metadata=metadata,
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


def _image_evidence(page: Any) -> str:
    try:
        resources = page.get("/Resources")
        if resources is None:
            return "absent"
        resources = _resolved_object(resources)
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return "absent"
        xobjects = _resolved_object(xobjects)
        for value in xobjects.values():
            if _resolved_object(value).get("/Subtype") == "/Image":
                return "present"
        return "absent"
    except Exception:
        return "unknown"


def _resolved_object(value: Any) -> Any:
    get_object = getattr(value, "get_object", None)
    return get_object() if get_object else value
