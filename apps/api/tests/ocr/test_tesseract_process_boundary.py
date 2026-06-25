from pathlib import Path

from app.infrastructure.ocr.failures import TesseractFailureReason
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import (
    OcrProcessRequest,
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)
from app.infrastructure.ocr.process_runner import PolicyBoundOcrProcessRunner


class FakeProcessBackend:
    def __init__(self, result: ProcessBoundaryResult | None = None, error: Exception | None = None) -> None:
        self.result = result or ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0, stdout="safe")
        self.error = error
        self.requests: list[ProcessBoundaryRequest] = []

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _request(**updates: object) -> OcrProcessRequest:
    values = {
        "image_handle": "PRIVATE_IMAGE_HANDLE",
        "argv": ("/opt/tesseract/bin/tesseract", "stdin", "stdout", "tsv"),
        "timeout_ms": 100,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
    }
    values.update(updates)
    return OcrProcessRequest(**values)  # type: ignore[arg-type]


def _runner(backend: FakeProcessBackend) -> PolicyBoundOcrProcessRunner:
    policy = ProcessExecutionPolicy(
        allowed_environment_keys=frozenset({"LANG"}),
        environment={"LANG": "C.UTF-8", "SECRET": "PRIVATE_ENV_SECRET"},
    )
    return PolicyBoundOcrProcessRunner(backend, policy)


def test_fake_boundary_receives_safe_policy_request_and_returns_success_output():
    backend = FakeProcessBackend()
    result = _runner(backend).run(_request())
    assert result.exit_code == 0
    assert result.stdout == "safe"
    boundary = backend.requests[0]
    assert boundary.argv == ("/opt/tesseract/bin/tesseract", "stdin", "stdout", "tsv")
    assert boundary.environment == (("LANG", "C.UTF-8"),)


def test_lifecycle_failures_map_to_internal_reasons_and_discard_partial_output():
    cases = {
        ProcessLifecycleState.SPAWN_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
        ProcessLifecycleState.TIMED_OUT: TesseractFailureReason.TIMEOUT,
        ProcessLifecycleState.NETWORK_ATTEMPTED: TesseractFailureReason.NETWORK_ATTEMPT,
        ProcessLifecycleState.TERMINATION_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
    }
    for state, expected in cases.items():
        backend = FakeProcessBackend(ProcessBoundaryResult(
            state=state,
            stdout="PRIVATE_PARTIAL_OCR_TEXT",
            stderr="PRIVATE_STDERR",
        ))
        result = _runner(backend).run(_request())
        assert result.failure_reason is expected
        assert result.stdout == ""


def test_backend_exception_and_unexpected_exit_fail_closed_without_raw_output():
    exception_result = _runner(FakeProcessBackend(error=RuntimeError("PRIVATE_STDERR"))).run(_request())
    exit_result = _runner(FakeProcessBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=2,
        stdout="PRIVATE_PARTIAL_OCR_TEXT",
        stderr="PRIVATE_STDERR",
    ))).run(_request())
    assert exception_result.failure_reason is TesseractFailureReason.PROCESS_SPAWN_FAILURE
    assert exit_result.failure_reason is TesseractFailureReason.UNEXPECTED_EXIT
    assert exception_result.stdout == ""
    assert exit_result.stdout == ""


def test_input_and_output_limits_fail_closed():
    input_result = _runner(FakeProcessBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        input_bytes=1001,
    ))).run(_request())
    output_result = _runner(FakeProcessBackend(ProcessBoundaryResult(
        state=ProcessLifecycleState.EXITED,
        exit_code=0,
        stdout="x" * 1001,
    ))).run(_request())
    assert input_result.failure_reason is TesseractFailureReason.PROCESS_SPAWN_FAILURE
    assert output_result.failure_reason is TesseractFailureReason.OUTPUT_LIMIT_EXCEEDED
    assert input_result.stdout == ""
    assert output_result.stdout == ""


def test_invalid_process_request_never_reaches_backend():
    backend = FakeProcessBackend()
    result = _runner(backend).run(_request(shell=True))
    assert result.failure_reason is TesseractFailureReason.PROCESS_SPAWN_FAILURE
    assert backend.requests == []


def test_j1_runner_is_fake_backend_orchestration_and_defers_os_process_to_j2():
    source = (Path(__file__).parents[2] / "app" / "infrastructure" / "ocr" / "process_runner.py").read_text(
        encoding="utf-8"
    )
    assert "injected fake backend for B3-J1" in source
    assert "real subprocess backend belongs to B3-J2" in source
