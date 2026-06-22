from dataclasses import dataclass
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
