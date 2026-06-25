"""PaddleOCR engine boundary with sanitized runtime output handling."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.types.common import PipelineFailure
from app.domain.types.parser import BlockLocation, OcrImageInput, OcrOptions, OcrResult, OcrTextBlock


@dataclass(frozen=True)
class PaddleOcrRuntimeConfig:
    enabled: bool = True


@dataclass(frozen=True)
class PaddleOcrRuntimeRequest:
    image_handle: str
    page: int | None
    languages: tuple[str, ...]
    timeout_ms: int


@dataclass(frozen=True)
class PaddleOcrRuntimeResult:
    status: Literal["success", "failed", "timeout", "unavailable"]
    blocks: list[dict[str, object]] | None = None
    stdout: str = ""
    stderr: str = ""
    error_detail: str = ""
    metadata: dict[str, object] | None = None


class PaddleOcrRuntimePort(Protocol):
    def recognize(self, request: PaddleOcrRuntimeRequest) -> PaddleOcrRuntimeResult: ...


class PaddleOcrEngine:
    """OcrEnginePort-compatible PaddleOCR adapter."""

    engine_id = "paddleocr-runtime"

    def __init__(
        self,
        config: PaddleOcrRuntimeConfig,
        runtime: PaddleOcrRuntimePort | None = None,
    ) -> None:
        self._config = config
        self._runtime = runtime

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        if self._runtime is None or not self._config.enabled:
            return _failure(self.engine_id, "OCR_ENGINE_UNAVAILABLE")
        try:
            runtime_result = self._runtime.recognize(PaddleOcrRuntimeRequest(
                image_handle=image.image_handle,
                page=image.page,
                languages=tuple(options.languages),
                timeout_ms=options.timeout_ms,
            ))
        except Exception:
            return _failure(_fake_engine_id(), "OCR_FAILED")
        if runtime_result.status == "unavailable":
            return _failure(_fake_engine_id(), "OCR_ENGINE_UNAVAILABLE")
        if runtime_result.status == "timeout":
            return _failure(_fake_engine_id(), "OCR_TIMEOUT", status="timeout")
        if runtime_result.status == "failed":
            return _failure(_fake_engine_id(), "OCR_FAILED")
        blocks = _safe_blocks(runtime_result.blocks or [])
        return OcrResult(
            status="text_found" if blocks else "no_text_detected",
            blocks=blocks,
            engine_id=_fake_engine_id(),
        )


def _fake_engine_id() -> str:
    return "paddleocr-runtime"


def _failure(
    engine_id: str,
    code: str,
    *,
    status: Literal["failed", "timeout"] = "failed",
) -> OcrResult:
        return OcrResult(
            status=status,
            blocks=[],
            engine_id=engine_id,
            failure=PipelineFailure(
                code=code,
                message=code,
                retryable=code in {"OCR_TIMEOUT", "OCR_FAILED"},
                module=engine_id,
            ),
        )


def _safe_blocks(raw_blocks: list[dict[str, object]]) -> list[OcrTextBlock]:
    blocks: list[OcrTextBlock] = []
    for raw in raw_blocks:
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            continue
        page = raw.get("page")
        blocks.append(OcrTextBlock(
            text=text,
            confidence_bucket=_confidence_bucket(raw.get("confidence")),
            location=BlockLocation(page=page if isinstance(page, int) and page > 0 else None),
        ))
    return blocks


def _confidence_bucket(value: object) -> Literal["low", "medium", "high", "unknown"]:
    if not isinstance(value, int | float):
        return "unknown"
    if value < 0:
        return "unknown"
    if value <= 1:
        value *= 100
    if value < 50:
        return "low"
    if value < 80:
        return "medium"
    return "high"


def compose_paddle_ocr_engine(
    config: PaddleOcrRuntimeConfig,
    runtime: PaddleOcrRuntimePort | None = None,
) -> PaddleOcrEngine:
    return PaddleOcrEngine(config, runtime)

