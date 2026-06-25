"""PR10B3-J4 temp-file privacy boundary over the existing fake process stack.

J1 implements the fake backend port, policy, and lifecycle orchestration.
J2 proves that real subprocess and production registration remain disabled.
J3 specifies fake process request/result/lifecycle and failure/privacy semantics.
J4 focuses on keeping temp-file-related sensitive values out of public results and failures.
"""

from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import (
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)
from app.infrastructure.ocr.process_runner import PolicyBoundOcrProcessRunner
from app.infrastructure.ocr.tesseract_adapter import TesseractOcrEngine
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig

PRIVATE_TEMP_PATH = "/PRIVATE_TEMP_PATH/runtime-input.png"
PRIVATE_ORIGINAL_FILENAME = "PRIVATE_ORIGINAL_FILENAME.png"
PRIVATE_IMAGE_HANDLE = f"PRIVATE_IMAGE_HANDLE:{PRIVATE_TEMP_PATH}:{PRIVATE_ORIGINAL_FILENAME}"
PRIVATE_OCR_TEXT = "PRIVATE_OCR_TEXT"
PRIVATE_PARTIAL_TEXT = "PRIVATE_PARTIAL_TEXT"
PRIVATE_STDERR = "PRIVATE_STDERR"
PRIVATE_ENV_SECRET = "PRIVATE_ENV_SECRET"
SYNTHETIC_SAFE_OCR_TEXT = "SYNTHETIC_SAFE_OCR_TEXT"
TSV_HEADER = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
PUBLIC_FAILURE_CODES = {"OCR_TIMEOUT", "OCR_ENGINE_UNAVAILABLE", "OCR_FAILED"}
SENSITIVE_VALUES = {
    PRIVATE_TEMP_PATH,
    PRIVATE_ORIGINAL_FILENAME,
    PRIVATE_IMAGE_HANDLE,
    PRIVATE_OCR_TEXT,
    PRIVATE_PARTIAL_TEXT,
    PRIVATE_STDERR,
    PRIVATE_ENV_SECRET,
}


class FakeVerifier:
    def path_exists(self, path: str) -> bool:
        return True

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return True


class SensitiveFakeBackend:
    def __init__(self, result: ProcessBoundaryResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests: list[ProcessBoundaryRequest] = []

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("fake result required")
        return self.result


def _config(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/synthetic/bin/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/synthetic/tessdata",
        "traineddata_sha256": {"kor": "b" * 64},
        "language_allowlist": frozenset({"kor"}),
        "production_package_pin_verified": True,
        "native_dependency_pins_verified": True,
        "platform": "linux",
        "platform_binary_verified": True,
        "max_timeout_ms": 1000,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
    }
    values.update(updates)
    return TesseractPreflightConfig(**values)  # type: ignore[arg-type]


def _recognize(
    backend: SensitiveFakeBackend,
    config: TesseractPreflightConfig | None = None,
):
    policy = ProcessExecutionPolicy(
        allowed_environment_keys=frozenset({"LANG"}),
        environment={"LANG": "C.UTF-8", "SECRET_TOKEN": PRIVATE_ENV_SECRET},
    )
    engine = TesseractOcrEngine(
        config or _config(),
        FakeVerifier(),
        PolicyBoundOcrProcessRunner(backend, policy),
    )
    return engine.recognize(
        OcrImageInput(image_handle=PRIVATE_IMAGE_HANDLE),
        OcrOptions(languages=["kor"], timeout_ms=500),
    )


def _serialized(result) -> str:
    return result.model_dump_json()


def _assert_sensitive_values_absent(result) -> None:
    serialized = _serialized(result)
    assert all(value not in serialized for value in SENSITIVE_VALUES)
    assert "ProcessBoundaryRequest" not in serialized
    assert "ProcessBoundaryResult" not in serialized
    if result.failure is not None:
        failure = result.failure.model_dump()
        assert set(failure) == {"code", "message", "retryable", "module"}
        assert failure["code"] in PUBLIC_FAILURE_CODES
        assert failure["message"] in PUBLIC_FAILURE_CODES


def test_success_returns_synthetic_ocr_text_without_temp_file_related_values():
    stdout = TSV_HEADER + f"5\t1\t1\t2\t3\t4\t91\t{SYNTHETIC_SAFE_OCR_TEXT}\n"
    backend = SensitiveFakeBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        stdout=stdout,
        stderr=PRIVATE_STDERR,
        input_bytes=100,
    ))
    result = _recognize(backend)
    assert result.status == "text_found"
    assert [block.text for block in result.blocks] == [SYNTHETIC_SAFE_OCR_TEXT]
    assert backend.requests[0].image_handle == PRIVATE_IMAGE_HANDLE
    assert backend.requests[0].environment == (("LANG", "C.UTF-8"),)
    _assert_sensitive_values_absent(result)


def test_lifecycle_failures_discard_partial_text_and_hide_temp_file_values():
    states = {
        ProcessLifecycleState.TIMED_OUT: "OCR_TIMEOUT",
        ProcessLifecycleState.SPAWN_FAILED: "OCR_FAILED",
        ProcessLifecycleState.NETWORK_ATTEMPTED: "OCR_FAILED",
        ProcessLifecycleState.TERMINATION_FAILED: "OCR_FAILED",
    }
    for state, expected_code in states.items():
        backend = SensitiveFakeBackend(ProcessBoundaryResult(
            state=state,
            stdout=f"{PRIVATE_OCR_TEXT}:{PRIVATE_PARTIAL_TEXT}:{PRIVATE_TEMP_PATH}",
            stderr=f"{PRIVATE_STDERR}:{PRIVATE_ORIGINAL_FILENAME}",
        ))
        result = _recognize(backend)
        assert result.blocks == []
        assert result.failure is not None
        assert result.failure.code == expected_code
        _assert_sensitive_values_absent(result)


def test_unexpected_exit_and_output_limit_hide_stdout_stderr_and_paths():
    unexpected = SensitiveFakeBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=2,
        stdout=f"{PRIVATE_PARTIAL_TEXT}:{PRIVATE_TEMP_PATH}",
        stderr=f"{PRIVATE_STDERR}:{PRIVATE_ORIGINAL_FILENAME}",
    ))
    oversized = SensitiveFakeBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        stdout=(PRIVATE_PARTIAL_TEXT + PRIVATE_TEMP_PATH) * 100,
        stderr=PRIVATE_STDERR,
    ))
    for result in (_recognize(unexpected), _recognize(oversized)):
        assert result.blocks == []
        assert result.failure is not None
        assert result.failure.code == "OCR_FAILED"
        _assert_sensitive_values_absent(result)


def test_backend_exception_message_and_internal_reason_do_not_become_public_failure_message():
    exception_message = f"{PRIVATE_STDERR}:{PRIVATE_TEMP_PATH}:{PRIVATE_ORIGINAL_FILENAME}"
    result = _recognize(SensitiveFakeBackend(error=RuntimeError(exception_message)))
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert result.failure.message == "OCR_FAILED"
    _assert_sensitive_values_absent(result)


def test_preflight_failure_hides_image_handle_and_does_not_reach_fake_backend():
    backend = SensitiveFakeBackend(ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0))
    result = _recognize(backend, _config(production_package_pin_verified=False))
    assert backend.requests == []
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    _assert_sensitive_values_absent(result)
