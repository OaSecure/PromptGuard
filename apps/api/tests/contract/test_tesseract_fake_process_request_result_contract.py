from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.failures import TesseractFailureReason
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import (
    OcrProcessRequest,
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)
from app.infrastructure.ocr.process_runner import PolicyBoundOcrProcessRunner
from app.infrastructure.ocr.tesseract_adapter import TesseractOcrEngine
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t91\tsafe text\n"
PUBLIC_FAILURE_CODES = {"OCR_TIMEOUT", "OCR_ENGINE_UNAVAILABLE", "OCR_FAILED"}


class FakeVerifier:
    def path_exists(self, path: str) -> bool:
        return True

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return True


class CapturingFakeBackend:
    def __init__(self, result: ProcessBoundaryResult) -> None:
        self.result = result
        self.requests: list[ProcessBoundaryRequest] = []

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        self.requests.append(request)
        return self.result


def _request(**updates: object) -> OcrProcessRequest:
    values = {
        "image_handle": "PRIVATE_IMAGE_HANDLE/customer-file.png",
        "argv": ("/private/bin/tesseract", "stdin", "stdout", "tsv"),
        "timeout_ms": 500,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
    }
    values.update(updates)
    return OcrProcessRequest(**values)  # type: ignore[arg-type]


def _policy_runner(backend: CapturingFakeBackend) -> PolicyBoundOcrProcessRunner:
    policy = ProcessExecutionPolicy(
        allowed_environment_keys=frozenset({"LANG", "OMP_THREAD_LIMIT"}),
        environment={
            "LANG": "C.UTF-8",
            "OMP_THREAD_LIMIT": "1",
            "SECRET_TOKEN": "PRIVATE_ENV_SECRET",
        },
    )
    return PolicyBoundOcrProcessRunner(backend, policy)


def _config(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/private/bin/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/private/tessdata",
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


def _engine_result(result: ProcessBoundaryResult, config: TesseractPreflightConfig | None = None):
    backend = CapturingFakeBackend(result)
    engine = TesseractOcrEngine(config or _config(), FakeVerifier(), _policy_runner(backend))
    ocr_result = engine.recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE/customer-file.png"),
        OcrOptions(languages=["kor"], timeout_ms=500),
    )
    return ocr_result, backend


def test_fake_backend_request_is_bounded_argv_only_and_environment_allowlisted():
    backend = CapturingFakeBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        stdout=TSV,
        input_bytes=100,
    ))
    result = _policy_runner(backend).run(_request())
    assert result.failure_reason is None
    captured = backend.requests[0]
    assert isinstance(captured.argv, tuple) and captured.argv
    assert captured.timeout_ms > 0
    assert captured.max_input_bytes > 0
    assert captured.max_output_bytes > 0
    assert captured.environment == (("LANG", "C.UTF-8"), ("OMP_THREAD_LIMIT", "1"))
    assert "PRIVATE_ENV_SECRET" not in repr(captured.environment)


def test_shell_network_download_and_invalid_bounds_fail_before_fake_backend():
    invalid_requests = [
        _request(shell=True),
        _request(allow_network_fallback=True),
        _request(allow_automatic_download=True),
        _request(timeout_ms=0),
        _request(max_input_bytes=0),
        _request(max_output_bytes=0),
        _request(argv=()),
    ]
    for request in invalid_requests:
        backend = CapturingFakeBackend(ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0))
        result = _policy_runner(backend).run(request)
        assert result.failure_reason is TesseractFailureReason.PROCESS_SPAWN_FAILURE
        assert result.stdout == ""
        assert backend.requests == []


def test_only_successful_exit_propagates_stdout_from_fake_boundary():
    success = ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0, stdout=TSV)
    result = _policy_runner(CapturingFakeBackend(success)).run(_request())
    assert result.exit_code == 0
    assert result.stdout == TSV


def test_lifecycle_failures_normalize_and_discard_partial_stdout_and_stderr():
    cases = {
        ProcessLifecycleState.TIMED_OUT: TesseractFailureReason.TIMEOUT,
        ProcessLifecycleState.SPAWN_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
        ProcessLifecycleState.NETWORK_ATTEMPTED: TesseractFailureReason.NETWORK_ATTEMPT,
        ProcessLifecycleState.TERMINATION_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
    }
    for state, reason in cases.items():
        boundary = ProcessBoundaryResult(
            state=state,
            stdout="PRIVATE_PARTIAL_OCR_TEXT",
            stderr="PRIVATE_STDERR",
        )
        result = _policy_runner(CapturingFakeBackend(boundary)).run(_request())
        assert result.failure_reason is reason
        assert result.stdout == ""
        assert "PRIVATE_STDERR" not in repr(result)

    unexpected = ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=2,
        stdout="PRIVATE_PARTIAL_OCR_TEXT",
        stderr="PRIVATE_STDERR",
    )
    result = _policy_runner(CapturingFakeBackend(unexpected)).run(_request())
    assert result.failure_reason is TesseractFailureReason.UNEXPECTED_EXIT
    assert result.stdout == ""


def test_input_and_output_limits_fail_closed_without_partial_result():
    oversized_input = ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        input_bytes=1001,
        stdout=TSV,
    )
    oversized_output = ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        stdout="PRIVATE_PARTIAL_OCR_TEXT" * 100,
    )
    input_result = _policy_runner(CapturingFakeBackend(oversized_input)).run(_request())
    output_result = _policy_runner(CapturingFakeBackend(oversized_output)).run(_request())
    assert input_result.failure_reason is TesseractFailureReason.PROCESS_SPAWN_FAILURE
    assert output_result.failure_reason is TesseractFailureReason.OUTPUT_LIMIT_EXCEEDED
    assert input_result.stdout == ""
    assert output_result.stdout == ""


def test_public_failure_and_response_do_not_expose_internal_or_sensitive_values():
    sensitive_values = {
        "PRIVATE_PARTIAL_OCR_TEXT",
        "PRIVATE_STDERR",
        "PRIVATE_IMAGE_HANDLE",
        "customer-file.png",
        "/private/bin/tesseract",
        "/private/tessdata",
        "PRIVATE_ENV_SECRET",
    }
    failure_results = [
        ProcessBoundaryResult(
            state=ProcessLifecycleState.TIMED_OUT,
            stdout="PRIVATE_PARTIAL_OCR_TEXT",
            stderr="PRIVATE_STDERR",
        ),
        ProcessBoundaryResult(
            state=ProcessLifecycleState.NETWORK_ATTEMPTED,
            stdout="PRIVATE_PARTIAL_OCR_TEXT",
            stderr="PRIVATE_STDERR",
        ),
        ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=2, stderr="PRIVATE_STDERR"),
    ]
    public_results = [_engine_result(result)[0] for result in failure_results]
    unavailable, backend = _engine_result(
        ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0),
        _config(production_package_pin_verified=False),
    )
    assert backend.requests == []
    public_results.append(unavailable)
    assert {result.failure.code for result in public_results if result.failure} <= PUBLIC_FAILURE_CODES
    assert {result.failure.code for result in public_results if result.failure} == {
        "OCR_TIMEOUT",
        "OCR_ENGINE_UNAVAILABLE",
        "OCR_FAILED",
    }
    serialized = "\n".join(result.model_dump_json() for result in public_results)
    assert all(secret not in serialized for secret in sensitive_values)
    assert all(f'"{reason.value}"' not in serialized for reason in TesseractFailureReason)
    assert all(result.blocks == [] for result in public_results)
