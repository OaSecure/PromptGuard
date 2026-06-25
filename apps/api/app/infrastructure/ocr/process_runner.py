"""Fallback OCR policy orchestration over an injected fake backend for B3-J1.

This module does not spawn an OS process. The real subprocess backend belongs to B3-J2.
"""

from .failures import TesseractFailureReason
from .process_policy import ProcessExecutionPolicy, request_satisfies_policy, safe_environment
from .process_port import (
    OcrProcessBackendPort,
    OcrProcessRequest,
    OcrProcessResult,
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)


class PolicyBoundOcrProcessRunner:
    """Fallback OCR process orchestration without an OS process implementation."""

    def __init__(self, backend: OcrProcessBackendPort, policy: ProcessExecutionPolicy) -> None:
        self._backend = backend
        self._policy = policy

    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        if not request_satisfies_policy(request):
            return _failure(TesseractFailureReason.PROCESS_SPAWN_FAILURE)
        boundary_request = ProcessBoundaryRequest(
            image_handle=request.image_handle,
            argv=request.argv,
            environment=safe_environment(self._policy),
            timeout_ms=request.timeout_ms,
            max_input_bytes=request.max_input_bytes,
            max_output_bytes=request.max_output_bytes,
        )
        try:
            result = self._backend.execute(boundary_request)
        except Exception:
            return _failure(TesseractFailureReason.PROCESS_SPAWN_FAILURE)
        return _sanitize_result(result, request)


def _sanitize_result(result: ProcessBoundaryResult, request: OcrProcessRequest) -> OcrProcessResult:
    state_reason = {
        ProcessLifecycleState.SPAWN_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
        ProcessLifecycleState.TIMED_OUT: TesseractFailureReason.TIMEOUT,
        ProcessLifecycleState.NETWORK_ATTEMPTED: TesseractFailureReason.NETWORK_ATTEMPT,
        ProcessLifecycleState.TERMINATION_FAILED: TesseractFailureReason.PROCESS_SPAWN_FAILURE,
    }.get(result.state)
    if state_reason is not None:
        return _failure(state_reason)
    if result.state is not ProcessLifecycleState.EXITED or result.exit_code != 0:
        return _failure(TesseractFailureReason.UNEXPECTED_EXIT)
    if result.input_bytes > request.max_input_bytes:
        return _failure(TesseractFailureReason.PROCESS_SPAWN_FAILURE)
    if len(result.stdout.encode("utf-8")) > request.max_output_bytes:
        return _failure(TesseractFailureReason.OUTPUT_LIMIT_EXCEEDED)
    return OcrProcessResult(exit_code=0, stdout=result.stdout)


def _failure(reason: TesseractFailureReason) -> OcrProcessResult:
    return OcrProcessResult(exit_code=None, stdout="", failure_reason=reason)
