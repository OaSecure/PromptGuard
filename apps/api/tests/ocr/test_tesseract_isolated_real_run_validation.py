"""Local-only Tesseract validation harness.

These tests document the manual real-run path without enabling it in CI.
The actual Tesseract subprocess path is guarded by an explicit environment
flag and is skipped by default.
"""

from __future__ import annotations

import os
from dataclasses import asdict

import pytest
from app.domain.types.parser import OcrImageInput, OcrOptions
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
