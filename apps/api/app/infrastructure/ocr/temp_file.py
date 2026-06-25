"""Secure temporary-input lifecycle around an injected OCR process runner.

The port owns concrete file creation and deletion. This coordinator only passes an
opaque runtime reference to the process boundary and sanitizes every lifecycle error.
"""

from dataclasses import dataclass, replace
from typing import Protocol

from .failures import TesseractFailureReason
from .process_port import OcrProcessRequest, OcrProcessResult, OcrProcessRunnerPort


@dataclass(frozen=True)
class StagedOcrInput:
    runtime_ref: str


class TemporaryFileLifecycleError(Exception):
    """Internal lifecycle error whose message must never cross the OCR boundary."""


class OcrTemporaryFilePort(Protocol):
    def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput: ...

    def release(self, staged_input: StagedOcrInput) -> None: ...


class SecureTemporaryFileProcessRunner:
    def __init__(
        self,
        temporary_files: OcrTemporaryFilePort,
        process_runner: OcrProcessRunnerPort,
    ) -> None:
        self._temporary_files = temporary_files
        self._process_runner = process_runner

    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        try:
            staged_input = self._temporary_files.stage(
                request.image_handle,
                request.max_input_bytes,
            )
        except Exception:
            return _temp_file_failure()

        try:
            result = self._process_runner.run(
                replace(request, image_handle=staged_input.runtime_ref)
            )
        except Exception:
            result = _process_failure()
        try:
            self._temporary_files.release(staged_input)
        except Exception:
            return _temp_file_failure()
        return result


def _temp_file_failure() -> OcrProcessResult:
    return OcrProcessResult(
        exit_code=None,
        stdout="",
        failure_reason=TesseractFailureReason.TEMP_FILE_FAILURE,
    )


def _process_failure() -> OcrProcessResult:
    return OcrProcessResult(
        exit_code=None,
        stdout="",
        failure_reason=TesseractFailureReason.PROCESS_SPAWN_FAILURE,
    )
