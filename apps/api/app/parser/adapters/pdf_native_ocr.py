from collections.abc import Callable
from typing import Literal

from app.domain.types.parser import OcrOptions
from app.infrastructure.pdf.pdfium_renderer import (
    InMemoryRenderedImageStore,
    PdfiumRenderer,
    RuntimePdfSourcePort,
)
from app.parser.adapters.pdf_foundation import PdfParserFoundationAdapter
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput
from app.parser.ports import ResolvedFileContentSourcePort
from app.ports.ocr import OcrEnginePort, PdfRendererPort

PdfRendererFactory = Callable[[RuntimePdfSourcePort], PdfRendererPort]


class PdfNativeOcrAdapter:
    def __init__(
        self,
        content_source: ResolvedFileContentSourcePort,
        ocr_engine: OcrEnginePort,
        *,
        max_ocr_pages: int = 3,
        timeout_ms: int = 60_000,
        languages: tuple[str, ...] = ("kor", "eng"),
        renderer_factory: PdfRendererFactory | None = None,
    ) -> None:
        self._native_adapter = PdfParserFoundationAdapter(content_source)
        self._content_source = content_source
        self._ocr_engine = ocr_engine
        self._max_ocr_pages = max_ocr_pages
        self._timeout_ms = timeout_ms
        self._languages = languages
        self._renderer_factory = renderer_factory or _default_renderer_factory

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if step.step_kind != "pdf_native_ocr" or payload.file_kind != "pdf":
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")
        if resolved_file is None or resolved_file.file_kind != "pdf":
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        return self._execute_supported_step(step, payload, resolved_file)

    def _execute_supported_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile,
    ) -> ParserStepResult:
        native_result = self._native_adapter.execute_step(
            step.model_copy(update={"step_kind": "pdf_native_text_extract"}),
            payload,
            resolved_file,
        )
        if native_result.document is None:
            return ParserStepResult(
                step_id=step.step_id,
                status="failed",
                trigger=native_result.trigger or "step_failed",
                failure=native_result.failure or sanitized_failure("PDF_PARSE_FAILED"),
            )

        coverage = PdfCoverageEvaluator().evaluate(
            tuple(
                PdfPageCoverageInput.model_validate(item)
                for item in native_result.document.metadata.get("page_coverage_inputs", ())
            ),
            max_ocr_pages=self._max_ocr_pages,
        )
        renderer = self._renderer_factory(_ResolvedPdfSource(self._content_source, resolved_file))
        integrated = PdfSelectedPageOcrIntegrator(renderer, self._ocr_engine).integrate(
            native_result.document,
            resolved_file.local_runtime_ref,
            coverage,
            OcrOptions(languages=list(self._languages), timeout_ms=self._timeout_ms),
        )
        status: Literal["success", "partial", "failed"] = "failed" if integrated.parser_status == "failed" else (
            "partial" if integrated.parser_status == "partial" else "success"
        )
        return ParserStepResult(
            step_id=step.step_id,
            status=status,
            document=integrated.document,
            failure=integrated.failure,
        )

    @staticmethod
    def _failure(step_id: str, code: str) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status="failed",
            trigger="step_failed",
            failure=sanitized_failure(code),
        )


class _ResolvedPdfSource:
    def __init__(
        self,
        content_source: ResolvedFileContentSourcePort,
        resolved_file: ResolvedTemporaryFile,
    ) -> None:
        self._content_source = content_source
        self._resolved_file = resolved_file

    def read(self, runtime_ref: str) -> bytes:
        if runtime_ref != self._resolved_file.local_runtime_ref:
            raise ValueError("runtime_ref_mismatch")
        return self._content_source.read(self._resolved_file)


def _default_renderer_factory(source: RuntimePdfSourcePort) -> PdfRendererPort:
    return PdfiumRenderer(source, InMemoryRenderedImageStore())
