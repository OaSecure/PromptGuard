"""Local-only Tesseract validation harness.

These tests document the manual real-run path without enabling it in CI.
The actual Tesseract subprocess path is guarded by an explicit environment
flag and is skipped by default.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest
from app.domain.types.parser import (
    OcrImageInput,
    OcrOptions,
    OcrResult,
    OcrTextBlock,
    ParsedBlock,
    ParsedDocument,
)
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import (
    OcrProcessBackendPort,
    OcrProcessRequest,
    OcrProcessResult,
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)
from app.infrastructure.ocr.tesseract_adapter import TesseractOcrEngine
from app.infrastructure.ocr.tesseract_composition import (
    DisabledTesseractOcrEngine,
    TesseractCompositionConfig,
    compose_tesseract_engine,
)
from app.infrastructure.ocr.tesseract_preflight import (
    TesseractArtifactVerifierPort,
    TesseractPreflightConfig,
)
from app.parser.readiness import REQUIRED_ARTIFACTS, validate_parser_ocr_readiness

RUN_REAL_VALIDATION_FLAG = "PROMPTGUARD_RUN_TESSERACT_REAL_VALIDATION"
TESSERACT_BINARY_ENV = "PROMPTGUARD_TESSERACT_BINARY"
TESSDATA_DIR_ENV = "PROMPTGUARD_TESSERACT_TESSDATA_DIR"
TESSERACT_LANG_ENV = "PROMPTGUARD_TESSERACT_LANG"
TESSERACT_PSM_ENV = "PROMPTGUARD_TESSERACT_PSM"

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t93\tlocal validation text\n"
SYNTHETIC_HELLO_OCR_PNG = (
    "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"
    "gg=="
)
PRIVATE_VALUES = (
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_ARGV",
    "C:\\private\\temp\\page.png",
    "private-original.pdf",
    "PRIVATE_RAW_EXCEPTION",
)


class FakeVerifier:
    def __init__(self, *, exists: bool = True, checksum: bool = True) -> None:
        self.exists = exists
        self.checksum = checksum
        self.checked_paths: list[str] = []

    def path_exists(self, path: str) -> bool:
        self.checked_paths.append(path)
        return self.exists

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        self.checked_paths.append(path)
        return self.checksum


class FakeBackend(OcrProcessBackendPort):
    def __init__(self, result: ProcessBoundaryResult | None = None) -> None:
        self.result = result or ProcessBoundaryResult(
            state=ProcessLifecycleState.EXITED,
            exit_code=0,
            stdout=TSV,
            stderr="",
        )
        self.requests: list[ProcessBoundaryRequest] = []

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        self.requests.append(request)
        return self.result


class RaisingBackend(OcrProcessBackendPort):
    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        raise AssertionError("real subprocess path must stay closed by default")


class FakeProcessRunner:
    def __init__(self, result: OcrProcessResult | None = None) -> None:
        self.result = result or OcrProcessResult(stdout=TSV)
        self.requests: list[OcrProcessRequest] = []

    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        self.requests.append(request)
        return self.result


def _config(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/opt/tesseract/bin/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/opt/tesseract/tessdata",
        "traineddata_sha256": {"eng": "b" * 64},
        "language_allowlist": frozenset({"eng"}),
        "production_package_pin_verified": True,
        "native_dependency_pins_verified": True,
        "platform": "linux",
        "platform_binary_verified": True,
        "max_timeout_ms": 1000,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
        "page_segmentation_mode": 6,
        "allowed_page_segmentation_modes": frozenset({3, 6}),
    }
    values.update(updates)
    return TesseractPreflightConfig(**values)  # type: ignore[arg-type]


def _manual_tesseract_env() -> tuple[Path, Path, str, str]:
    binary = Path(os.environ.get(TESSERACT_BINARY_ENV, ""))
    tessdata = Path(os.environ.get(TESSDATA_DIR_ENV, ""))
    language = os.environ.get(TESSERACT_LANG_ENV, "eng")
    psm = os.environ.get(TESSERACT_PSM_ENV, "6")
    missing = [
        name
        for name, value in (
            (TESSERACT_BINARY_ENV, str(binary)),
            (TESSDATA_DIR_ENV, str(tessdata)),
        )
        if not value
    ]
    if missing:
        pytest.skip(f"set {', '.join(missing)} for isolated local Tesseract validation")
    if not binary.exists():
        pytest.skip("configured Tesseract binary is unavailable")
    if not (tessdata / f"{language}.traineddata").exists():
        pytest.skip("configured Tesseract traineddata is unavailable")
    return binary, tessdata, language, psm


def _options() -> OcrOptions:
    return OcrOptions(languages=["eng"], timeout_ms=500)


def _image() -> OcrImageInput:
    return OcrImageInput(image_handle="opaque-local-validation-image", page=1)


def _real_validation_enabled() -> bool:
    return os.environ.get(RUN_REAL_VALIDATION_FLAG) == "1"


def _skip_reason() -> str | None:
    if _real_validation_enabled():
        return None
    return f"set {RUN_REAL_VALIDATION_FLAG}=1 to run isolated local Tesseract validation"


def _manual_config_from_environment() -> TesseractPreflightConfig:
    language = os.environ.get(TESSERACT_LANG_ENV, "eng")
    return _config(
        binary_path=os.environ.get(TESSERACT_BINARY_ENV, ""),
        tessdata_directory=os.environ.get(TESSDATA_DIR_ENV, ""),
        traineddata_sha256={language: "manual-validation-checksum-required"},
        language_allowlist=frozenset({language}),
        page_segmentation_mode=int(os.environ.get(TESSERACT_PSM_ENV, "6")),
    )


def _assert_public_result_is_sanitized(result: object) -> None:
    serialized = str(result)
    assert all(value not in serialized for value in PRIVATE_VALUES)


def _write_synthetic_image(directory: Path) -> Path:
    image_path = directory / "synthetic_ocr_validation.png"
    image_path.write_bytes(base64.b64decode(SYNTHETIC_HELLO_OCR_PNG))
    return image_path


def _write_synthetic_korean_image(directory: Path) -> Path:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    image_path = directory / "synthetic_korean_ocr_validation.png"
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    font = ImageFont.truetype(str(font_path), 120) if font_path.exists() else None
    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 55), "개인정보", fill="black", font=font)
    image.save(image_path)
    return image_path


def _ocr_result_from_local_validation(text: str) -> OcrResult:
    return OcrResult(
        status="text_found",
        blocks=[
            OcrTextBlock(
                text=text,
                confidence_bucket="unknown",
            ),
        ],
        engine_id="tesseract-local-only-validation",
    )


def _parsed_document_from_ocr_result(result: OcrResult) -> ParsedDocument:
    return ParsedDocument(
        input_id="local-only-synthetic-input",
        file_ref="opaque-local-only-synthetic-ref",
        file_kind="image",
        parser_id="tesseract-local-only-validation",
        parser_version="test-only",
        parser_status="parsed",
        ocr_status=result.status,
        blocks=[
            ParsedBlock(
                block_id=f"ocr-block-{index}",
                input_id="local-only-synthetic-input",
                text=block.text,
                source="ocr",
                location=None,
                extraction_status="extracted",
            )
            for index, block in enumerate(result.blocks)
        ],
        metadata={"validation_scope": "local-only"},
    )


def test_isolated_real_run_validation_is_skipped_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(RUN_REAL_VALIDATION_FLAG, raising=False)

    assert _skip_reason() == f"set {RUN_REAL_VALIDATION_FLAG}=1 to run isolated local Tesseract validation"

    engine = compose_tesseract_engine(
        TesseractCompositionConfig(preflight=_config(), enabled=False),
        verifier=FakeVerifier(),
        temporary_files=None,
        backend=RaisingBackend(),
        process_policy=ProcessExecutionPolicy(allowed_environment_keys=frozenset(), environment={}),
    )

    assert isinstance(engine, DisabledTesseractOcrEngine)


def test_opt_in_flag_is_required_before_any_local_validation_path_opens(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(RUN_REAL_VALIDATION_FLAG, raising=False)

    reason = _skip_reason()

    assert reason is not None
    assert RUN_REAL_VALIDATION_FLAG in reason


@pytest.mark.parametrize(
    ("verifier", "expected_code"),
    [
        (FakeVerifier(exists=False), "OCR_ENGINE_UNAVAILABLE"),
        (FakeVerifier(checksum=False), "OCR_ENGINE_UNAVAILABLE"),
    ],
)
def test_opt_in_preflight_failures_stop_before_process(verifier: TesseractArtifactVerifierPort, expected_code: str):
    runner = FakeProcessRunner()
    engine = TesseractOcrEngine(_config(), verifier, runner)

    result = engine.recognize(_image(), _options())

    assert result.failure is not None
    assert result.failure.code == expected_code
    assert runner.requests == []
    _assert_public_result_is_sanitized(result)


def test_fake_backend_success_path_exposes_only_ocr_text():
    runner = FakeProcessRunner()
    engine = TesseractOcrEngine(_config(), FakeVerifier(), runner)

    result = engine.recognize(_image(), _options())

    assert result.status == "text_found"
    assert [block.text for block in result.blocks] == ["local validation text"]
    assert result.failure is None
    serialized = result.model_dump(mode="json")
    assert serialized["blocks"][0]["text"] == "local validation text"
    assert "metadata" not in serialized
    assert "failure" in serialized
    _assert_public_result_is_sanitized(serialized)


def test_validation_failures_do_not_expose_process_diagnostics():
    runner = FakeProcessRunner(OcrProcessResult(exit_code=2, stdout="PRIVATE_STDOUT"))
    engine = TesseractOcrEngine(_config(), FakeVerifier(), runner)

    result = engine.recognize(_image(), _options())

    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert result.blocks == []
    _assert_public_result_is_sanitized(result)


def test_validation_harness_does_not_change_readiness_approval_state():
    inventory = {name: {} for name in REQUIRED_ARTIFACTS}

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert set(asdict(result)) == {"ready", "reason_codes"}


def test_manual_real_run_validation_requires_explicit_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(RUN_REAL_VALIDATION_FLAG, raising=False)
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    config = _manual_config_from_environment()

    assert config.binary_path
    assert config.tessdata_directory


def test_manual_real_run_validation_executes_one_synthetic_ocr_when_explicitly_enabled():
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)
    binary, tessdata, language, psm = _manual_tesseract_env()
    temp_dir_path: Path | None = None
    image_path: Path | None = None

    with tempfile.TemporaryDirectory(prefix="promptguard_tesseract_validation_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        image_path = _write_synthetic_image(temp_dir_path)
        completed = subprocess.run(
            [
                str(binary),
                str(image_path),
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
        }
        ocr_result = _ocr_result_from_local_validation(public_validation_result["text"])
        parsed_document = _parsed_document_from_ocr_result(ocr_result)
        serialized_document = parsed_document.model_dump(mode="json")

        assert completed.returncode == 0
        assert "HELLO OCR" in public_validation_result["text"]
        assert [block.text for block in ocr_result.blocks] == [public_validation_result["text"]]
        assert [block["text"] for block in serialized_document["blocks"]] == [public_validation_result["text"]]
        assert "HELLO OCR" not in str(serialized_document["metadata"])
        assert ocr_result.failure is None
        assert all(block["location"] is None for block in serialized_document["blocks"])
        assert completed.stderr is not None
        _assert_public_result_is_sanitized(public_validation_result)
        _assert_public_result_is_sanitized(ocr_result.model_dump(mode="json"))
        _assert_public_result_is_sanitized(serialized_document)
        assert str(binary) not in str(public_validation_result)
        assert str(tessdata) not in str(public_validation_result)
        assert str(image_path) not in str(public_validation_result)
        assert str(binary) not in str(serialized_document)
        assert str(tessdata) not in str(serialized_document)
        assert str(image_path) not in str(serialized_document)
        assert temp_dir_path.exists()
        assert image_path.exists()

    assert temp_dir_path is not None
    assert image_path is not None
    assert not image_path.exists()
    assert not temp_dir_path.exists()


def test_manual_real_run_validation_recognizes_korean_fixture_when_kor_is_configured():
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)
    binary, tessdata, language, psm = _manual_tesseract_env()
    if language != "kor":
        pytest.skip(f"set {TESSERACT_LANG_ENV}=kor to run Korean OCR validation")

    with tempfile.TemporaryDirectory(prefix="promptguard_tesseract_kor_validation_") as temp_dir:
        image_path = _write_synthetic_korean_image(Path(temp_dir))
        completed = subprocess.run(
            [
                str(binary),
                str(image_path),
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
        recognized = "".join(completed.stdout.split())
        expected = "개인정보"
        public_status_only = {"exit_code": completed.returncode}

        assert completed.returncode == 0
        assert expected in recognized, "Tesseract Korean OCR did not recognize the controlled fixture text"
        assert str(binary) not in str(public_status_only)
        assert str(tessdata) not in str(public_status_only)
        assert str(image_path) not in str(public_status_only)
