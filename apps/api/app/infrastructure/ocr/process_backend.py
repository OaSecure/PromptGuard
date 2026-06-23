"""Opt-in OS subprocess backend for the isolated Tesseract process boundary."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .process_port import (
    ProcessBoundaryRequest,
    ProcessBoundaryResult,
    ProcessLifecycleState,
)

ProcessFactory = Callable[..., Any]
InputReader = Callable[[str], bytes]


class SubprocessOcrProcessBackend:
    """Execute a preflight-approved argv without exposing process diagnostics."""

    def __init__(
        self,
        *,
        process_factory: ProcessFactory = subprocess.Popen,
        input_reader: InputReader | None = None,
    ) -> None:
        self._process_factory = process_factory
        self._input_reader = input_reader or _read_input

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult:
        try:
            image_bytes = self._input_reader(request.image_handle)
        except Exception:
            return _failed()
        input_bytes = len(image_bytes)
        if input_bytes > request.max_input_bytes:
            return _failed()

        try:
            process = self._process_factory(
                request.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(request.environment),
                shell=False,
            )
        except Exception:
            return _failed()

        try:
            stdout, _stderr = process.communicate(
                input=image_bytes,
                timeout=request.timeout_ms / 1000,
            )
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.communicate()
            except Exception:
                return ProcessBoundaryResult(state=ProcessLifecycleState.TERMINATION_FAILED)
            return ProcessBoundaryResult(state=ProcessLifecycleState.TIMED_OUT)
        except Exception:
            return _failed()

        if len(stdout) > request.max_output_bytes:
            return _failed()
        try:
            safe_stdout = stdout.decode("utf-8", errors="strict")
        except (AttributeError, UnicodeDecodeError):
            return _failed()
        return ProcessBoundaryResult(
            state=ProcessLifecycleState.EXITED,
            exit_code=process.returncode,
            stdout=safe_stdout,
            stderr="",
            input_bytes=input_bytes,
        )


def _read_input(runtime_ref: str) -> bytes:
    return Path(runtime_ref).read_bytes()


def _failed() -> ProcessBoundaryResult:
    return ProcessBoundaryResult(state=ProcessLifecycleState.SPAWN_FAILED)
