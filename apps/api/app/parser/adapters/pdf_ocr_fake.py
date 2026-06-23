import logging

from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrOptions
from app.parser.models import FileParserResult, sanitized_failure
from app.parser.pdf_coverage import PdfCoverageResult
from app.ports.ocr import OcrEnginePort, PdfRendererPort

logger = logging.getLogger(__name__)

_MERGED_DOCUMENT_METADATA_KEYS = frozenset({"page_coverage_inputs", "failed_page_indices"})


class PdfSelectedPageOcrIntegrator:
    """Consume PR8 page selections and integrate OCR results without re-evaluating coverage."""

    def __init__(self, renderer: PdfRendererPort, ocr_engine: OcrEnginePort) -> None:
        self._renderer = renderer
        self._ocr_engine = ocr_engine

    def integrate(
        self,
        native_document: ParsedDocument,
        runtime_ref: str,
        coverage: PdfCoverageResult,
        options: OcrOptions,
    ) -> FileParserResult:
        ocr_blocks: list[ParsedBlock] = []
        failure_code: str | None = None
        statuses: list[str] = []

        if coverage.aggregate.skipped_candidate_count:
            failure_code = "OCR_PAGE_LIMIT_EXCEEDED"

        for page_index in _selected_candidate_pages(coverage):
            try:
                image = self._renderer.render_page(runtime_ref, page_index)
            except Exception:
                logger.error("PDF page rendering failed", extra={"failure_code": "PDF_RENDER_FAILED"})
                failure_code = failure_code or "PDF_RENDER_FAILED"
                statuses.append("failed")
                continue
            try:
                ocr_result = self._ocr_engine.recognize(image, options)
            except Exception:
                logger.error("OCR recognition failed", extra={"failure_code": "OCR_FAILED"})
                failure_code = failure_code or "OCR_FAILED"
                statuses.append("failed")
                continue
            statuses.append(ocr_result.status)
            if ocr_result.status == "failed":
                failure_code = failure_code or "OCR_FAILED"
                continue
            for ordinal, block in enumerate(ocr_result.blocks, start=1):
                if not block.text:
                    continue
                ocr_blocks.append(ParsedBlock(
                    block_id=f"pdf-ocr-page-{page_index}-block-{ordinal}",
                    input_id=native_document.input_id,
                    text=block.text,
                    source_type="pdf_ocr_page",
                    location={"kind": "pdf", "page": page_index},
                ))

        merged = sorted(
            [*native_document.blocks, *ocr_blocks],
            key=lambda block: (_page(block), 0 if block.source_type == "pdf_native_page" else 1, block.block_id),
        )
        if ocr_blocks:
            ocr_status = "text_found"
        elif "failed" in statuses:
            ocr_status = "failed"
        elif coverage.aggregate.selected_candidate_pages:
            ocr_status = "no_text_detected"
        else:
            ocr_status = "not_applicable"
        document = native_document.model_copy(update={
            "blocks": merged,
            "parser_id": "pdf-native-plus-fake-ocr",
            "parser_status": "partial" if failure_code else "parsed",
            "ocr_status": ocr_status,
            "metadata": _safe_merge_metadata(native_document),
        })
        return FileParserResult(
            input_id=native_document.input_id,
            document=document,
            parser_status="partial" if failure_code else "parsed",
            ocr_status=ocr_status,
            failure=sanitized_failure(failure_code) if failure_code else None,
        )


def _page(block: ParsedBlock) -> int:
    if isinstance(block.location, dict):
        page = block.location.get("page")
        if isinstance(page, int):
            return page
    return 2**31 - 1


def _safe_merge_metadata(document: ParsedDocument) -> dict:
    return {
        key: value
        for key, value in document.metadata.items()
        if key in _MERGED_DOCUMENT_METADATA_KEYS
    }


def _selected_candidate_pages(coverage: PdfCoverageResult) -> tuple[int, ...]:
    aggregate_selected = set(coverage.aggregate.selected_candidate_pages)
    return tuple(
        page.page_index
        for page in coverage.pages
        if page.selected_for_ocr and page.is_ocr_candidate and page.page_index in aggregate_selected
    )
