"""Lazy, production-disabled Paddle OCR runtime skeleton."""

from dataclasses import dataclass
from importlib import import_module as default_import_module
from typing import Callable

from .paddle_candidate import PaddleOcrCandidateRequest, PaddleOcrCandidateRuntimeResult


@dataclass(frozen=True)
class PaddleOcrLazyRuntimeConfig:
    manual_opt_in: bool = False
    model_directory: str | None = None
    allow_remote_fetch: bool = False
    allow_automatic_download: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allow_remote_fetch", False)
        object.__setattr__(self, "allow_automatic_download", False)


class PaddleOcrLazyRuntimeSkeleton:
    """Manual-only runtime boundary that defers optional dependency import."""

    def __init__(
        self,
        config: PaddleOcrLazyRuntimeConfig,
        *,
        import_module: Callable[[str], object] = default_import_module,
    ) -> None:
        self._config = config
        self._import_module = import_module

    def recognize(self, request: PaddleOcrCandidateRequest) -> PaddleOcrCandidateRuntimeResult:
        del request
        if not self._config.manual_opt_in:
            return PaddleOcrCandidateRuntimeResult(status="unavailable")
        try:
            self._import_module("paddleocr")
        except ModuleNotFoundError:
            return PaddleOcrCandidateRuntimeResult(status="unavailable")
        except Exception:
            return PaddleOcrCandidateRuntimeResult(status="failed")
        return PaddleOcrCandidateRuntimeResult(status="unavailable")
