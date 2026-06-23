"""Local-only rendered-image OCR boundary validation.

This test intentionally stops at the PDF rendered-image handoff boundary.
It does not execute a PDF renderer or enable production OCR wiring.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
from app.atoms.models import ParsedBlock as AtomParsedBlock
from app.atoms.models import ParsedDocument as AtomParsedDocument
from app.domain.types.parser import (
    BlockLocation,
    OcrImageInput,
    OcrOptions,
    OcrResult,
    OcrTextBlock,
    ParsedBlock,
    ParsedDocument,
)
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput
from app.parser.readiness import REQUIRED_ARTIFACTS, validate_parser_ocr_readiness
from test_tesseract_isolated_real_run_validation import SYNTHETIC_HELLO_OCR_PNG

RUN_REAL_VALIDATION_FLAG = "PROMPTGUARD_RUN_TESSERACT_REAL_VALIDATION"
TESSERACT_BINARY_ENV = "PROMPTGUARD_TESSERACT_BINARY"
TESSDATA_DIR_ENV = "PROMPTGUARD_TESSERACT_TESSDATA_DIR"
TESSERACT_LANG_ENV = "PROMPTGUARD_TESSERACT_LANG"
TESSERACT_PSM_ENV = "PROMPTGUARD_TESSERACT_PSM"

PRIVATE_VALUES = (
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_ARGV",
    "PRIVATE_RAW_EXCEPTION",
    "private-original.pdf",
)


@dataclass(frozen=True)
class RenderedImageHandoff:
    runtime_ref: Path
    page_index: int
    source_kind: str = "synthetic-rendered-image"

    def public_metadata(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "page_count": 1,
        }


class LocalOnlyRenderedImageRenderer:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.calls: list[tuple[str, int]] = []
        self.released: list[str] = []

    def render_page(self, runtime_ref: str, page: int) -> OcrImageInput:
        self.calls.append((runtime_ref, page))
        handoff = _write_rendered_image(self.directory)
        return OcrImageInput(image_handle=str(handoff.runtime_ref), page=page)

    def release(self, image: OcrImageInput) -> None:
        self.released.append(image.image_handle)
        Path(image.image_handle).unlink(missing_ok=True)


class LocalOnlyTesseractCliEngine:
    engine_id = "tesseract-local-only-pdf-pipeline-validation"

    def __init__(self, binary: Path, tessdata: Path, language: str, psm: str) -> None:
        self.binary = binary
        self.tessdata = tessdata
        self.language = language
        self.psm = psm
        self.calls: list[str] = []

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        self.calls.append(image.image_handle)
        completed = subprocess.run(
            [
                str(self.binary),
                image.image_handle,
                "stdout",
                "--tessdata-dir",
                str(self.tessdata),
                "-l",
                self.language,
                "--psm",
                self.psm,
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(options.timeout_ms / 1000, 10),
        )
        if completed.returncode != 0:
            return OcrResult(status="failed", blocks=[], engine_id=self.engine_id)
        text = completed.stdout.strip()
        return OcrResult(
            status="text_found" if text else "no_text_detected",
            blocks=[] if not text else [
                OcrTextBlock(
                    text=text,
                    confidence_bucket="unknown",
                    location=BlockLocation(page=image.page),
                ),
            ],
            engine_id=self.engine_id,
        )


def _skip_reason() -> str | None:
    if os.environ.get(RUN_REAL_VALIDATION_FLAG) == "1":
        return None
    return f"set {RUN_REAL_VALIDATION_FLAG}=1 to run local-only rendered-image OCR validation"


def _manual_tesseract_env() -> tuple[Path, Path, str, str]:
    binary = Path(os.environ.get(TESSERACT_BINARY_ENV, ""))
    tessdata = Path(os.environ.get(TESSDATA_DIR_ENV, ""))
    language = os.environ.get(TESSERACT_LANG_ENV, "eng")
    psm = os.environ.get(TESSERACT_PSM_ENV, "6")
    if not str(binary):
        pytest.skip(f"set {TESSERACT_BINARY_ENV} for local-only rendered-image OCR validation")
    if not str(tessdata):
        pytest.skip(f"set {TESSDATA_DIR_ENV} for local-only rendered-image OCR validation")
    if not binary.exists():
        pytest.skip("configured Tesseract binary is unavailable")
    if not (tessdata / f"{language}.traineddata").exists():
        pytest.skip("configured Tesseract traineddata is unavailable")
    return binary, tessdata, language, psm


def _write_rendered_image(directory: Path) -> RenderedImageHandoff:
    image_path = directory / "synthetic_rendered_page.png"
    image_path.write_bytes(base64.b64decode(SYNTHETIC_HELLO_OCR_PNG))
    return RenderedImageHandoff(runtime_ref=image_path, page_index=0)


def _native_pdf_document() -> AtomParsedDocument:
    return AtomParsedDocument(
        input_id="local-only-pdf-input",
        file_ref="opaque-local-only-pdf-ref",
        file_type="pdf",
        parser_id="pdf-native-test-only",
        parser_status="parsed",
        ocr_status="not_applicable",
        blocks=[
            AtomParsedBlock(
                block_id="pdf-native-page-2",
                input_id="local-only-pdf-input",
                text="native page two",
                source_type="pdf_native_page",
                location={"kind": "pdf", "page": 2},
            ),
        ],
        metadata={
            "page_coverage_inputs": [
                {
                    "page_index": 1,
                    "native_extraction_status": "success",
                    "meaningful_character_count": 0,
                    "image_evidence": "unknown",
                },
            ],
            "failed_page_indices": [],
            "temp_path": "C:\\private\\rendered-page.png",
            "runtime_ref": "PRIVATE_RUNTIME_REF",
            "original_filename": "private-original.pdf",
            "raw_exception": "PRIVATE_RAW_EXCEPTION",
        },
    )


def _coverage_for_single_ocr_page():
    return PdfCoverageEvaluator().evaluate(
        [
            PdfPageCoverageInput(
                page_index=1,
                native_extraction_status="success",
                meaningful_character_count=0,
                image_evidence="unknown",
            ),
            PdfPageCoverageInput(
                page_index=2,
                native_extraction_status="success",
                meaningful_character_count=120,
                image_evidence="unknown",
            ),
        ],
        max_ocr_pages=1,
    )


def _ocr_result_from_rendered_image_text(text: str) -> OcrResult:
    return OcrResult(
        status="text_found",
        blocks=[
            OcrTextBlock(
                text=text,
                confidence_bucket="unknown",
                location=BlockLocation(page=1),
            ),
        ],
        engine_id="tesseract-local-only-rendered-image-validation",
    )


def _parsed_document_from_ocr_result(result: OcrResult, handoff: RenderedImageHandoff) -> ParsedDocument:
    return ParsedDocument(
        input_id="local-only-rendered-image-input",
        file_ref="opaque-local-only-rendered-image-ref",
        file_kind="pdf",
        parser_id="tesseract-local-only-rendered-image-validation",
        parser_version="test-only",
        parser_status="parsed",
        ocr_status=result.status,
        blocks=[
            ParsedBlock(
                block_id=f"ocr-page-{block.location.page if block.location else index}",
                input_id="local-only-rendered-image-input",
                text=block.text,
                source="ocr",
                location=block.location,
                extraction_status="extracted",
            )
            for index, block in enumerate(result.blocks)
        ],
        metadata=handoff.public_metadata(),
    )


def _assert_not_exposed(surface: object, *extra_private_values: object) -> None:
    serialized = str(surface)
    private_values = (*PRIVATE_VALUES, *(str(value) for value in extra_private_values))
    assert all(value not in serialized for value in private_values)


def test_rendered_image_boundary_real_ocr_is_skip_by_default():
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)


def test_local_only_rendered_image_boundary_runs_one_real_ocr_and_maps_text_to_document():
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)
    binary, tessdata, language, psm = _manual_tesseract_env()
    temp_dir_path: Path | None = None
    image_path: Path | None = None

    with tempfile.TemporaryDirectory(prefix="promptguard_rendered_image_ocr_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        handoff = _write_rendered_image(temp_dir_path)
        image_path = handoff.runtime_ref

        completed = subprocess.run(
            [
                str(binary),
                str(handoff.runtime_ref),
                "stdout",
                "--tessdata-dir",
                str(tessdata),
                "-l",
                language,
                "--psm",
                psm,
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        public_validation_result = {
            "exit_code": completed.returncode,
            "text": completed.stdout.strip(),
            "boundary": handoff.public_metadata(),
        }
        ocr_result = _ocr_result_from_rendered_image_text(public_validation_result["text"])
        parsed_document = _parsed_document_from_ocr_result(ocr_result, handoff)
        serialized_document = parsed_document.model_dump(mode="json")

        assert completed.returncode == 0
        assert "HELLO OCR" in public_validation_result["text"]
        assert [block.text for block in ocr_result.blocks] == [public_validation_result["text"]]
        assert [block["text"] for block in serialized_document["blocks"]] == [public_validation_result["text"]]
        assert "HELLO OCR" not in str(serialized_document["metadata"])
        assert ocr_result.failure is None
        assert all(block["location"] == {"page": 1, "sheet_index": None, "slide": None, "line_start": None, "line_end": None} for block in serialized_document["blocks"])
        assert completed.stderr is not None
        _assert_not_exposed(public_validation_result, binary, tessdata, image_path)
        _assert_not_exposed(ocr_result.model_dump(mode="json"), binary, tessdata, image_path)
        _assert_not_exposed(serialized_document, binary, tessdata, image_path)
        assert temp_dir_path.exists()
        assert image_path.exists()

    assert temp_dir_path is not None
    assert image_path is not None
    assert not image_path.exists()
    assert not temp_dir_path.exists()


def test_local_only_rendered_image_validation_keeps_readiness_fail_closed():
    inventory = {name: {} for name in REQUIRED_ARTIFACTS}

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert set(asdict(result)) == {"ready", "reason_codes"}


def test_local_only_pdf_ocr_pipeline_maps_rendered_image_text_to_document_without_private_leaks():
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)
    binary, tessdata, language, psm = _manual_tesseract_env()
    temp_dir_path: Path | None = None
    released_image_path: Path | None = None

    with tempfile.TemporaryDirectory(prefix="promptguard_pdf_ocr_pipeline_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        renderer = LocalOnlyRenderedImageRenderer(temp_dir_path)
        engine = LocalOnlyTesseractCliEngine(binary, tessdata, language, psm)
        result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
            _native_pdf_document(),
            "PRIVATE_RUNTIME_REF",
            _coverage_for_single_ocr_page(),
            OcrOptions(languages=[language], timeout_ms=1000),
        )
        released_image_path = Path(renderer.released[0])

        assert renderer.calls == [("PRIVATE_RUNTIME_REF", 1)]
        assert len(engine.calls) == 1
        assert result.failure is None
        assert result.document is not None
        ocr_blocks = [
            block
            for block in result.document.blocks
            if block.source_type == "pdf_ocr_page"
        ]
        assert [block.text for block in ocr_blocks] == ["HELLO OCR"]
        assert result.document.ocr_status == "text_found"
        assert result.document.metadata == {
            "page_coverage_inputs": [
                {
                    "page_index": 1,
                    "native_extraction_status": "success",
                    "meaningful_character_count": 0,
                    "image_evidence": "unknown",
                },
            ],
            "failed_page_indices": [],
        }
        non_text_output = result.model_dump()
        for block in non_text_output["document"]["blocks"]:
            block.pop("text", None)
        _assert_not_exposed(non_text_output, binary, tessdata, released_image_path)
        assert "HELLO OCR" not in str(non_text_output)
        assert not released_image_path.exists()
        assert temp_dir_path.exists()

    assert temp_dir_path is not None
    assert released_image_path is not None
    assert not released_image_path.exists()
    assert not temp_dir_path.exists()
