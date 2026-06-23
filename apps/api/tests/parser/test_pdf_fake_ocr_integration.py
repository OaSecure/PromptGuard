import json
import logging

from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrOptions, OcrResult, OcrTextBlock
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.fakes import FakeOcrEngine, FakePdfRenderer
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput


class TrackingPdfRenderer(FakePdfRenderer):
    def __init__(self, fail_pages: set[int] | None = None) -> None:
        super().__init__(fail_pages)
        self.released: list[int | None] = []

    def release(self, image) -> None:
        self.released.append(image.page)


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


def test_inconsistent_coverage_aggregate_cannot_expand_ocr_pages():
    coverage = PdfCoverageEvaluator().evaluate([_page(1), _page(2, 120)], 1)
    forged_coverage = coverage.model_copy(update={
        "aggregate": coverage.aggregate.model_copy(update={"selected_candidate_pages": (1, 2)})
    })
    renderer = FakePdfRenderer()
    engine = FakeOcrEngine(text_by_page={1: "ocr page one", 2: "must not run"})

    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "PRIVATE_RUNTIME_REF", forged_coverage, OcrOptions(timeout_ms=1000)
    )

    assert renderer.calls == [1]
    assert engine.calls == [1]
    assert [(block.location["page"], block.source_type) for block in result.document.blocks] == [
        (1, "pdf_ocr_page"), (2, "pdf_native_page")
    ]


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
    renderer = TrackingPdfRenderer()
    engine = FakeOcrEngine(exception_message="PRIVATE_RAW_EXCEPTION C:\\private\\secret.pdf")
    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(), "PRIVATE_RUNTIME_REF", coverage, OcrOptions(timeout_ms=1000)
    )
    exposed = result.failure.message + repr(result.failure.metadata) + repr(result.document.metadata) + caplog.text
    assert result.parser_status == "partial"
    assert result.failure.code == "OCR_FAILED"
    for forbidden in ("PRIVATE_RAW_EXCEPTION", "secret.pdf", "PRIVATE_RUNTIME_REF", "file_ref", "base64"):
        assert forbidden not in exposed
    assert renderer.released == [1]


def test_rendered_image_is_released_after_success():
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 1)
    renderer = TrackingPdfRenderer()
    result = PdfSelectedPageOcrIntegrator(renderer, FakeOcrEngine(text_by_page={1: "safe"})).integrate(
        _native_document(), "runtime", coverage, OcrOptions(timeout_ms=1000)
    )
    assert result.document.ocr_status == "text_found"
    assert renderer.released == [1]


def test_fake_ocr_merge_does_not_propagate_private_runtime_metadata():
    safe_coverage_metadata = [{
        "page_index": 1,
        "native_extraction_status": "success",
        "meaningful_character_count": 0,
        "image_evidence": "unknown",
    }]
    native_document = _native_document().model_copy(update={
        "metadata": {
            "page_coverage_inputs": safe_coverage_metadata,
            "failed_page_indices": [3],
            "temp_path": "C:\\private\\rendered-page.png",
            "runtime_ref": "PRIVATE_RUNTIME_REF",
            "original_filename": "private-original.pdf",
            "raw_exception": "PRIVATE_RAW_EXCEPTION",
        }
    })
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 1)
    renderer = FakePdfRenderer()
    engine = FakeOcrEngine(text_by_page={1: "PRIVATE_OCR_TEXT"})

    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        native_document, "PRIVATE_RUNTIME_REF", coverage, OcrOptions(timeout_ms=1000)
    )

    assert result.document.metadata == {
        "page_coverage_inputs": safe_coverage_metadata,
        "failed_page_indices": [3],
    }
    ocr_block = next(
        block for block in result.document.blocks if block.source_type == "pdf_ocr_page"
    )
    assert ocr_block.text == "PRIVATE_OCR_TEXT"
    assert ocr_block.metadata == {}
    assert ocr_block.location == {"kind": "pdf", "page": 1}
    non_text_output = result.model_dump()
    for block in non_text_output["document"]["blocks"]:
        block.pop("text", None)
    serialized = json.dumps(non_text_output, sort_keys=True)
    for private_value in (
        "PRIVATE_OCR_TEXT",
        "C:\\private\\rendered-page.png",
        "PRIVATE_RUNTIME_REF",
        "private-original.pdf",
        "PRIVATE_RAW_EXCEPTION",
    ):
        assert private_value not in serialized
    assert set(type(result).model_fields).isdisjoint(
        {"action", "reason_code", "user_notice", "event", "storage"}
    )


def test_fake_ocr_merge_rebuilds_duplicate_blocks_deterministically_without_engine_metadata():
    class DuplicateBlockEngine:
        engine_id = "fake-duplicate-ocr"

        def recognize(self, image, options):
            return OcrResult(
                status="text_found",
                engine_id=self.engine_id,
                blocks=[
                    OcrTextBlock(
                        text="first OCR block",
                        confidence_bucket="high",
                        location={"page": image.page},
                    ),
                    OcrTextBlock(
                        text="second OCR block",
                        confidence_bucket="low",
                        location={"page": image.page},
                    ),
                ],
            )

    native_document = _native_document()
    coverage = PdfCoverageEvaluator().evaluate([_page(1)], 1)
    options = OcrOptions(timeout_ms=1000)
    original_document = native_document.model_dump()
    original_coverage = coverage.model_dump()
    original_options = options.model_dump()

    result = PdfSelectedPageOcrIntegrator(
        FakePdfRenderer(), DuplicateBlockEngine()
    ).integrate(native_document, "PRIVATE_RUNTIME_REF", coverage, options)

    ocr_blocks = [
        block for block in result.document.blocks if block.source_type == "pdf_ocr_page"
    ]
    assert [block.block_id for block in ocr_blocks] == [
        "pdf-ocr-page-1-block-1",
        "pdf-ocr-page-1-block-2",
    ]
    assert [block.text for block in ocr_blocks] == ["first OCR block", "second OCR block"]
    assert all(block.metadata == {} for block in ocr_blocks)
    assert all(block.location == {"kind": "pdf", "page": 1} for block in ocr_blocks)
    assert native_document.model_dump() == original_document
    assert coverage.model_dump() == original_coverage
    assert options.model_dump() == original_options


def test_fake_ocr_contract_returns_typed_result():
    engine = FakeOcrEngine(text_by_page={1: "text"})
    image = FakePdfRenderer().render_page("runtime", 1)
    result = engine.recognize(image, OcrOptions(timeout_ms=1000))
    assert isinstance(result, OcrResult)
    assert result.blocks == [OcrTextBlock(text="text", confidence_bucket="unknown", location={"page": 1})]
