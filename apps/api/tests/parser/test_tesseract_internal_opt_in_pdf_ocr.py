import base64
import hashlib
import os
import sys
from pathlib import Path

import pytest
from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.parser_composition import ParserOcrEngineSelectionConfig, select_parser_ocr_engine
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import ProcessBoundaryResult, ProcessLifecycleState
from app.infrastructure.ocr.temp_file import StagedOcrInput
from app.infrastructure.ocr.tesseract_composition import (
    DisabledTesseractOcrEngine,
    TesseractCompositionConfig,
)
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.fakes import FakeOcrEngine
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput

sys.path.insert(0, str(Path(__file__).parents[1] / "ocr"))
from test_tesseract_isolated_real_run_validation import SYNTHETIC_HELLO_OCR_PNG

RUN_REAL_VALIDATION_FLAG = "PROMPTGUARD_RUN_TESSERACT_REAL_VALIDATION"
TESSERACT_BINARY_ENV = "PROMPTGUARD_TESSERACT_BINARY"
TESSDATA_DIR_ENV = "PROMPTGUARD_TESSERACT_TESSDATA_DIR"
TESSERACT_LANG_ENV = "PROMPTGUARD_TESSERACT_LANG"
TESSERACT_PSM_ENV = "PROMPTGUARD_TESSERACT_PSM"

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t91\tinternal opt in text\n"
PRIVATE_VALUES = (
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_ARGV",
    "PRIVATE_RAW_EXCEPTION",
    "PRIVATE_RUNTIME_REF",
    "private-original.pdf",
)


class FakeVerifier:
    def __init__(self, *, exists: bool = True, checksum: bool = True) -> None:
        self.exists = exists
        self.checksum = checksum

    def path_exists(self, path: str) -> bool:
        return self.exists

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return self.checksum


class FileHashVerifier:
    def path_exists(self, path: str) -> bool:
        return Path(path).exists()

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_sha256.lower()


class FakeTempFiles:
    def __init__(self) -> None:
        self.staged: list[str] = []
        self.released: list[str] = []

    def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput:
        self.staged.append(image_handle)
        return StagedOcrInput(runtime_ref=image_handle)

    def release(self, staged_input: StagedOcrInput) -> None:
        self.released.append(staged_input.runtime_ref)


class FakeBackend:
    def __init__(self, result: ProcessBoundaryResult | None = None) -> None:
        self.result = result or ProcessBoundaryResult(
            state=ProcessLifecycleState.EXITED,
            exit_code=0,
            stdout=TSV,
            input_bytes=10,
        )
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return self.result


class LocalRenderedImageRenderer:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.calls: list[tuple[str, int]] = []
        self.released: list[str] = []

    def render_page(self, runtime_ref: str, page: int) -> OcrImageInput:
        self.calls.append((runtime_ref, page))
        image_path = self.directory / "internal_opt_in_rendered_page.png"
        image_path.write_bytes(base64.b64decode(SYNTHETIC_HELLO_OCR_PNG))
        return OcrImageInput(image_handle=str(image_path), page=page)

    def release(self, image: OcrImageInput) -> None:
        self.released.append(image.image_handle)
        Path(image.image_handle).unlink(missing_ok=True)


def _preflight(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/fake/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/fake/tessdata",
        "traineddata_sha256": {"eng": "b" * 64},
        "language_allowlist": frozenset({"eng"}),
        "production_package_pin_verified": True,
        "native_dependency_pins_verified": True,
        "platform": "linux",
        "platform_binary_verified": True,
        "max_timeout_ms": 1000,
        "max_input_bytes": 100000,
        "max_output_bytes": 100000,
        "page_segmentation_mode": 6,
        "allowed_page_segmentation_modes": frozenset({3, 6}),
    }
    values.update(updates)
    return TesseractPreflightConfig(**values)  # type: ignore[arg-type]


def _selection_config(*, use_tesseract: bool = False, tesseract_enabled: bool = False, preflight=None):
    return ParserOcrEngineSelectionConfig(
        use_tesseract=use_tesseract,
        tesseract=TesseractCompositionConfig(
            enabled=tesseract_enabled,
            preflight=preflight or _preflight(),
        ),
    )


def _policy() -> ProcessExecutionPolicy:
    return ProcessExecutionPolicy(allowed_environment_keys=frozenset(), environment={})


def _native_document() -> ParsedDocument:
    return ParsedDocument(
        input_id="internal-opt-in-input",
        file_ref="opaque-internal-opt-in-ref",
        file_type="pdf",
        parser_id="pdf-native-test-only",
        parser_status="parsed",
        ocr_status="not_applicable",
        blocks=[
            ParsedBlock(
                block_id="pdf-native-page-2",
                input_id="internal-opt-in-input",
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
            "runtime_ref": "PRIVATE_RUNTIME_REF",
            "original_filename": "private-original.pdf",
            "raw_exception": "PRIVATE_RAW_EXCEPTION",
        },
    )


def _coverage():
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


def _assert_not_exposed(surface: object, *extra_private_values: object) -> None:
    serialized = str(surface)
    private_values = (*PRIVATE_VALUES, *(str(value) for value in extra_private_values))
    assert all(value not in serialized for value in private_values)


def _manual_tesseract_env() -> tuple[Path, Path, str, str]:
    binary = Path(os.environ.get(TESSERACT_BINARY_ENV, ""))
    tessdata = Path(os.environ.get(TESSDATA_DIR_ENV, ""))
    language = os.environ.get(TESSERACT_LANG_ENV, "eng")
    psm = os.environ.get(TESSERACT_PSM_ENV, "6")
    if not str(binary):
        pytest.skip(f"set {TESSERACT_BINARY_ENV} for local-only internal opt-in validation")
    if not str(tessdata):
        pytest.skip(f"set {TESSDATA_DIR_ENV} for local-only internal opt-in validation")
    if not binary.exists():
        pytest.skip("configured Tesseract binary is unavailable")
    if not (tessdata / f"{language}.traineddata").exists():
        pytest.skip("configured Tesseract traineddata is unavailable")
    return binary, tessdata, language, psm


def test_default_selection_keeps_existing_fake_engine_without_touching_tesseract_ports():
    default_engine = FakeOcrEngine(text_by_page={1: "default fake"})
    backend = FakeBackend()

    selected = select_parser_ocr_engine(
        _selection_config(),
        default_engine=default_engine,
        verifier=FakeVerifier(),
        temporary_files=FakeTempFiles(),
        backend=backend,
        process_policy=_policy(),
    )

    assert selected is default_engine
    assert backend.calls == 0


def test_explicit_opt_in_selects_tesseract_candidate_and_integrator_receives_ocr_text():
    backend = FakeBackend()
    temporary_files = FakeTempFiles()
    engine = select_parser_ocr_engine(
        _selection_config(use_tesseract=True, tesseract_enabled=True),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=FakeVerifier(),
        temporary_files=temporary_files,
        backend=backend,
        process_policy=_policy(),
    )
    renderer = LocalRenderedImageRenderer(Path(os.environ.get("TEMP", ".")))

    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(),
        "PRIVATE_RUNTIME_REF",
        _coverage(),
        OcrOptions(languages=["eng"], timeout_ms=500),
    )

    assert backend.calls == 1
    assert temporary_files.staged
    assert temporary_files.released == temporary_files.staged
    assert result.document is not None
    ocr_blocks = [block for block in result.document.blocks if block.source_type == "pdf_ocr_page"]
    assert [block.text for block in ocr_blocks] == ["internal opt in text"]
    non_text_output = result.model_dump()
    for block in non_text_output["document"]["blocks"]:
        block.pop("text", None)
    _assert_not_exposed(non_text_output)
    assert "internal opt in text" not in str(non_text_output)


@pytest.mark.parametrize(
    ("verifier", "temporary_files", "policy"),
    [
        (None, FakeTempFiles(), _policy()),
        (FakeVerifier(), None, _policy()),
        (FakeVerifier(), FakeTempFiles(), None),
        (FakeVerifier(exists=False), FakeTempFiles(), _policy()),
        (FakeVerifier(checksum=False), FakeTempFiles(), _policy()),
    ],
)
def test_opt_in_missing_dependency_or_preflight_failure_is_fail_closed(verifier, temporary_files, policy):
    engine = select_parser_ocr_engine(
        _selection_config(use_tesseract=True, tesseract_enabled=True),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=verifier,
        temporary_files=temporary_files,
        backend=FakeBackend(),
        process_policy=policy,
    )
    result = engine.recognize(
        OcrImageInput(image_handle="PRIVATE_RUNTIME_REF", page=1),
        OcrOptions(languages=["eng"], timeout_ms=500),
    )

    assert isinstance(engine, DisabledTesseractOcrEngine) or result.failure is not None
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    _assert_not_exposed(result.model_dump(mode="json"))


def test_local_only_internal_opt_in_real_ocr_is_skip_by_default():
    if os.environ.get(RUN_REAL_VALIDATION_FLAG) != "1":
        pytest.skip(f"set {RUN_REAL_VALIDATION_FLAG}=1 to run local-only internal opt-in OCR validation")


def test_local_only_internal_opt_in_real_ocr_pipeline_maps_text_without_private_leaks(tmp_path):
    if os.environ.get(RUN_REAL_VALIDATION_FLAG) != "1":
        pytest.skip(f"set {RUN_REAL_VALIDATION_FLAG}=1 to run local-only internal opt-in OCR validation")
    binary, tessdata, language, psm = _manual_tesseract_env()
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    traineddata_sha = hashlib.sha256((tessdata / f"{language}.traineddata").read_bytes()).hexdigest()
    renderer = LocalRenderedImageRenderer(tmp_path)
    temporary_files = FakeTempFiles()
    engine = select_parser_ocr_engine(
        _selection_config(
            use_tesseract=True,
            tesseract_enabled=True,
            preflight=_preflight(
                binary_path=str(binary),
                binary_sha256=binary_sha,
                tessdata_directory=str(tessdata),
                traineddata_sha256={language: traineddata_sha},
                language_allowlist=frozenset({language}),
                platform="windows",
                platform_binary_verified=True,
                max_timeout_ms=1000,
                page_segmentation_mode=int(psm),
            ),
        ),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=FileHashVerifier(),
        temporary_files=temporary_files,
        backend=None,
        process_policy=_policy(),
    )

    result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
        _native_document(),
        "PRIVATE_RUNTIME_REF",
        _coverage(),
        OcrOptions(languages=[language], timeout_ms=1000),
    )

    assert result.failure is None
    assert result.document is not None
    ocr_blocks = [block for block in result.document.blocks if block.source_type == "pdf_ocr_page"]
    assert " ".join(block.text for block in ocr_blocks) == "HELLO OCR"
    assert temporary_files.staged == renderer.released
    assert all(not Path(path).exists() for path in renderer.released)
    non_text_output = result.model_dump()
    for block in non_text_output["document"]["blocks"]:
        block.pop("text", None)
    _assert_not_exposed(non_text_output, binary, tessdata, *renderer.released)
    assert "HELLO" not in str(non_text_output)
    assert "OCR" not in str(non_text_output)
