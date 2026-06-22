from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .failures import TesseractFailureReason


@dataclass(frozen=True)
class OcrProcessRequest:
    image_handle: str
    argv: tuple[str, ...]
    timeout_ms: int
    max_input_bytes: int
    max_output_bytes: int
    shell: bool = False
    allow_network_fallback: bool = False
    allow_automatic_download: bool = False


@dataclass(frozen=True)
class OcrProcessResult:
    exit_code: int | None = 0
    stdout: str = ""
    failure_reason: TesseractFailureReason | None = None


class OcrProcessRunnerPort(Protocol):
    def run(self, request: OcrProcessRequest) -> OcrProcessResult: ...


class ProcessLifecycleState(str, Enum):
    EXITED = "EXITED"
    SPAWN_FAILED = "SPAWN_FAILED"
    TIMED_OUT = "TIMED_OUT"
    NETWORK_ATTEMPTED = "NETWORK_ATTEMPTED"
    TERMINATION_FAILED = "TERMINATION_FAILED"


@dataclass(frozen=True)
class ProcessBoundaryRequest:
    image_handle: str
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    timeout_ms: int
    max_input_bytes: int
    max_output_bytes: int


@dataclass(frozen=True)
class ProcessBoundaryResult:
    state: ProcessLifecycleState
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    input_bytes: int = 0


class OcrProcessBackendPort(Protocol):
    """J1 test-double boundary; an OS subprocess backend is deferred to B3-J2."""

    def execute(self, request: ProcessBoundaryRequest) -> ProcessBoundaryResult: ...
