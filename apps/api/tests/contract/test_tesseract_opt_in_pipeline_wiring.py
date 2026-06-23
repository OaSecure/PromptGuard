from app.atoms.models import ParsedDocument
from app.domain.types.parser import OcrOptions
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import ProcessBoundaryResult, ProcessLifecycleState
from app.infrastructure.ocr.temp_file import StagedOcrInput
from app.infrastructure.ocr.tesseract_composition import (
    DisabledTesseractOcrEngine,
    TesseractCompositionConfig,
    compose_tesseract_engine,
)
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.fakes import FakePdfRenderer
from app.parser.pdf_coverage import PdfCoverageEvaluator, PdfPageCoverageInput

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t91\tsafe opt in text\n"


class FakeVerifier:
    def __init__(self, *, missing: str | None = None, mismatch: str | None = None) -> None:
        self.missing = missing
        self.mismatch = mismatch

    def path_exists(self, path: str) -> bool:
        return self.missing is None or self.missing not in path

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return self.mismatch is None or self.mismatch not in path


class FakeTempFiles:
    def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput:
        return StagedOcrInput(runtime_ref="opaque-staged-input")

    def release(self, staged_input: StagedOcrInput) -> None:
        return None


class FakeBackend:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ProcessBoundaryResult(
            state=ProcessLifecycleState.EXITED,
            exit_code=0,
            stdout=TSV,
            input_bytes=10,
        )


class BackendFactory:
    def __init__(self) -> None:
        self.calls = 0
        self.backend = FakeBackend()

    def __call__(self):
        self.calls += 1
        return self.backend


def _preflight() -> TesseractPreflightConfig:
    return TesseractPreflightConfig(
        binary_path="/verified/tesseract",
        binary_sha256="a" * 64,
        tessdata_directory="/verified/tessdata",
        traineddata_sha256={"kor": "b" * 64},
        language_allowlist=frozenset({"kor"}),
        production_package_pin_verified=True,
        native_dependency_pins_verified=True,
        platform="linux",
        platform_binary_verified=True,
        max_timeout_ms=1000,
        max_input_bytes=1000,
        max_output_bytes=1000,
    )


def _compose(*, enabled=False, verifier=None, backend=None, backend_factory=None):
    return compose_tesseract_engine(
        TesseractCompositionConfig(preflight=_preflight(), enabled=enabled),
        verifier=verifier or FakeVerifier(),
        temporary_files=FakeTempFiles(),
        backend=backend,
        backend_factory=backend_factory,
        process_policy=ProcessExecutionPolicy(frozenset({"LANG"}), {"LANG": "C.UTF-8"}),
    )


def test_default_config_is_disabled_and_does_not_select_backend_candidate():
    factory = BackendFactory()
    engine = compose_tesseract_engine(
        TesseractCompositionConfig(preflight=_preflight()),
        verifier=FakeVerifier(),
        temporary_files=FakeTempFiles(),
        backend=None,
        backend_factory=factory,
        process_policy=ProcessExecutionPolicy(frozenset(), {}),
    )
    assert isinstance(engine, DisabledTesseractOcrEngine)
    assert factory.calls == 0


def test_explicit_opt_in_selects_backend_candidate_without_executing_it():
    factory = BackendFactory()
    engine = _compose(enabled=True, backend_factory=factory)
    assert not isinstance(engine, DisabledTesseractOcrEngine)
    assert factory.calls == 1
    assert factory.backend.calls == 0


def test_opt_in_preflight_failures_stop_before_backend_execution():
    for verifier in (
        FakeVerifier(missing="tesseract"),
        FakeVerifier(missing="kor.traineddata"),
        FakeVerifier(mismatch="kor.traineddata"),
    ):
        backend = FakeBackend()
        result = _compose(enabled=True, verifier=verifier, backend=backend).recognize(
            image={"image_handle": "opaque-image", "page": 1},
            options=OcrOptions(languages=["kor"], timeout_ms=500),
        )
        assert result.failure is not None
        assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
        assert backend.calls == 0


def test_explicit_opt_in_flows_fake_backend_text_into_parsed_block_only():
    backend = FakeBackend()
    engine = _compose(enabled=True, backend=backend)
    coverage = PdfCoverageEvaluator().evaluate([
        PdfPageCoverageInput(
            page_index=1,
            native_extraction_status="success",
            meaningful_character_count=0,
            image_evidence="unknown",
        )
    ], 1)
    native = ParsedDocument(
        input_id="input-1",
        blocks=[],
        file_type="pdf",
        parser_id="pdf-native-pypdf",
        parser_status="parsed",
        metadata={},
    )
    result = PdfSelectedPageOcrIntegrator(FakePdfRenderer(), engine).integrate(
        native, "opaque-runtime-ref", coverage, OcrOptions(languages=["kor"], timeout_ms=500)
    )
    assert result.document is not None
    assert [block.text for block in result.document.blocks] == ["safe opt in text"]
    assert result.document.blocks[0].metadata == {}
    assert result.document.blocks[0].location == {"kind": "pdf", "page": 1}
    assert "safe opt in text" not in repr(result.document.metadata)
    assert backend.calls == 1
