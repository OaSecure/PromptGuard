import io
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.atoms.models import ParsedDocument
from app.domain.types.parser import BlockLocation, OcrImageInput, OcrOptions, OcrResult, OcrTextBlock
from app.infrastructure.pdf.pdfium_renderer import InMemoryRenderedImageStore, PdfiumRenderer
from app.parser.adapters.pdf_foundation import PdfParserFoundationAdapter
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.models import ParserPlanStep, ParserWorkerPayload, ResolvedTemporaryFile, TempFileAccessContext
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput
from app.ports.ocr import OcrEnginePort


class ParserFixtureReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ready: bool
    blockers: list[str]
    pdf_native_status: str
    pdf_native_block_count: int
    pdf_render_status: Literal["success", "failed"]
    rendered_image_count: int
    pdf_ocr_status: str
    pdf_ocr_block_count: int


class ParserFixtureReadinessProbe:
    """Runs local synthetic parser fixtures and emits metadata-only readiness."""

    def check(self) -> ParserFixtureReadinessReport:
        pdf_bytes = _synthetic_text_pdf()
        native = _run_pdf_native_fixture(pdf_bytes)
        render_status, rendered_count = _run_pdf_render_fixture(pdf_bytes)
        ocr_result = _run_pdf_ocr_fixture()
        blockers = [
            code
            for code, failed in (
                ("pdf_native_fixture_failed", native.status != "success"),
                ("pdf_render_fixture_failed", render_status != "success"),
                ("pdf_ocr_fixture_failed", ocr_result.parser_status != "parsed"),
            )
            if failed
        ]
        return ParserFixtureReadinessReport(
            ready=not blockers,
            blockers=blockers,
            pdf_native_status=native.status,
            pdf_native_block_count=len(native.document.blocks) if native.document else 0,
            pdf_render_status=render_status,
            rendered_image_count=rendered_count,
            pdf_ocr_status=ocr_result.parser_status,
            pdf_ocr_block_count=len(ocr_result.document.blocks) if ocr_result.document else 0,
        )


class _ContentSource:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        del resolved_file
        return self._content


class _RuntimePdfSource:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self, runtime_ref: str) -> bytes:
        del runtime_ref
        return self._content


class _FixtureOcrEngine(OcrEnginePort):
    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        del options
        return OcrResult(
            status="text_found",
            blocks=[OcrTextBlock(text="fixture ocr text", confidence_bucket="high", location=BlockLocation(page=image.page))],
            engine_id="fixture-ocr",
        )


def _synthetic_text_pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 20 100 Td (fixture native text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()


def _payload() -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="fixture-input",
        request_id="fixture-request",
        input_kind="file_reference",
        extraction_requirement="native_parse_then_ocr_fallback",
        file_ref="opaque-fixture-file-ref",
        file_kind="pdf",
        access_context=TempFileAccessContext(
            authenticated_subject_id="fixture-subject",
            session_id="fixture-session",
            request_id="fixture-request",
        ),
    )


def _step() -> ParserPlanStep:
    return ParserPlanStep(
        step_id="fixture-pdf-native",
        ordinal=0,
        step_kind="pdf_native_text_extract",
        capability_id="fixture-pdf",
    )


def _resolved() -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(
        file_ref="opaque-fixture-file-ref",
        file_kind="pdf",
        local_runtime_ref="opaque-runtime-ref",
    )


def _run_pdf_native_fixture(pdf_bytes: bytes):
    return PdfParserFoundationAdapter(_ContentSource(pdf_bytes)).execute_step(_step(), _payload(), _resolved())


def _run_pdf_render_fixture(pdf_bytes: bytes) -> tuple[Literal["success", "failed"], int]:
    store = InMemoryRenderedImageStore()
    renderer = PdfiumRenderer(_RuntimePdfSource(pdf_bytes), store, scale=1)
    try:
        image = renderer.render_page("opaque-runtime-ref", 1)
    except Exception:
        return "failed", 0
    try:
        return "success", 1
    finally:
        renderer.release(image)


def _run_pdf_ocr_fixture():
    native = ParsedDocument(
        input_id="fixture-input",
        blocks=[],
        file_ref="opaque-fixture-file-ref",
        file_type="pdf",
        parser_id="fixture-native",
        parser_status="parsed",
        ocr_status="not_applicable",
        metadata={
            "page_coverage_inputs": [
                {
                    "page_index": 1,
                    "native_extraction_status": "success",
                    "meaningful_character_count": 0,
                    "image_evidence": "unknown",
                }
            ]
        },
    )
    coverage = PdfCoverageEvaluator().evaluate(
        [
            PdfPageCoverageInput(
                page_index=1,
                native_extraction_status="success",
                meaningful_character_count=0,
                image_evidence="unknown",
            )
        ],
        1,
    )
    renderer = _SingleImageRenderer()
    return PdfSelectedPageOcrIntegrator(renderer, _FixtureOcrEngine()).integrate(
        native,
        "opaque-runtime-ref",
        coverage,
        OcrOptions(languages=["kor"], timeout_ms=1000),
    )


class _SingleImageRenderer:
    def render_page(self, runtime_ref: str, page: int) -> OcrImageInput:
        del runtime_ref
        return OcrImageInput(image_handle="opaque-rendered-image", page=page)

    def release(self, image: OcrImageInput) -> None:
        del image
