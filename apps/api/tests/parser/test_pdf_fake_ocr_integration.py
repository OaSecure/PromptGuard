import logging

from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrOptions, OcrResult, OcrTextBlock
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.fakes import FakeOcrEngine, FakePdfRenderer
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput


def _page(page_index: int, count: int = 0) -> PdfPageCoverageInput:
    return PdfPageCoverageInput(
        page_index=page_index,
        native_extraction_status="success",
        meaningful_character_count=count,
        image_evidence="unknown",
    )


def _native_document() -> ParsedDocument:
    return ParsedDocument(
        input_id="input-1",
        blocks=[ParsedBlock(
            block_id="pdf-page-2", input_id="input-1", text="native page two",
            source_type="pdf_native_page", location={"kind": "pdf", "page": 2},
        )],
        file_type="pdf",
        parser_id="pdf-native-pypdf",
        parser_status="parsed",
        metadata={},
    )


def test_only_pr8_selected_pages_are_rendered_and_ocr_runs_in_page_order():
    coverage = PdfCoverageEvaluator().evaluate([_page(3), _page(1), _page(2, 120)], 1)
    renderer = FakePdfRenderer()
    engine = FakeOcrEngine(text_by_page={1: "ocr page one", 3: "must not run"})

    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "PRIVATE_RUNTIME_REF", coverage, OcrOptions(timeout_ms=1000)
    )

    assert renderer.calls == [1]
    assert engine.calls == [1]
    assert [(block.location["page"], block.source_type) for block in result.document.blocks] == [
        (1, "pdf_ocr_page"), (2, "pdf_native_page")
    ]
    assert result.parser_status == "partial"
    assert result.failure.code == "OCR_PAGE_LIMIT_EXCEEDED"


def test_no_selected_pages_does_not_render_or_run_ocr():
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 0)
    renderer, engine = FakePdfRenderer(), FakeOcrEngine()
    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "runtime", coverage, OcrOptions(timeout_ms=1000)
    )
    assert renderer.calls == []
    assert engine.calls == []
    assert result.failure.code == "OCR_PAGE_LIMIT_EXCEEDED"


def test_no_text_ocr_does_not_create_blank_block():
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 1)
    renderer, engine = FakePdfRenderer(), FakeOcrEngine(text_by_page={1: ""})
    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "runtime", coverage, OcrOptions(timeout_ms=1000)
    )
    assert len(result.document.blocks) == 1
    assert result.document.ocr_status == "no_text_detected"


def test_page_failure_preserves_native_and_successful_ocr_blocks():
    coverage = PdfCoverageEvaluator().evaluate([_page(1), _page(3)], 2)
    renderer = FakePdfRenderer(fail_pages={3})
    engine = FakeOcrEngine(text_by_page={1: "ocr success"})
    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "runtime", coverage, OcrOptions(timeout_ms=1000)
    )
    assert [(block.location["page"], block.text) for block in result.document.blocks] == [
        (1, "ocr success"), (2, "native page two")
    ]
    assert result.parser_status == "partial"
    assert result.failure.code == "PDF_RENDER_FAILED"


def test_ocr_failure_is_sanitized_and_preserves_available_blocks(caplog):
    caplog.set_level(logging.ERROR)
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 1)
    renderer = FakePdfRenderer()
    engine = FakeOcrEngine(exception_message="PRIVATE_RAW_EXCEPTION C:\\private\\secret.pdf")
    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "PRIVATE_RUNTIME_REF", coverage, OcrOptions(timeout_ms=1000)
    )
    exposed = result.failure.message + repr(result.failure.metadata) + repr(result.document.metadata) + caplog.text
    assert result.parser_status == "partial"
    assert result.failure.code == "OCR_FAILED"
    for forbidden in ("PRIVATE_RAW_EXCEPTION", "secret.pdf", "PRIVATE_RUNTIME_REF", "file_ref", "base64"):
        assert forbidden not in exposed


def test_fake_ocr_contract_returns_typed_result():
    engine = FakeOcrEngine(text_by_page={1: "text"})
    image = FakePdfRenderer().render_page("runtime", 1)
    result = engine.recognize(image, OcrOptions(timeout_ms=1000))
    assert isinstance(result, OcrResult)
    assert result.blocks == [OcrTextBlock(text="text", confidence_bucket="unknown", location={"page": 1})]
