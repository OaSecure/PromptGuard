"""Install-free, production-disabled boundary for a possible OCR candidate."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.types.common import PipelineFailure
from app.domain.types.parser import BlockLocation, OcrImageInput, OcrOptions, OcrResult, OcrTextBlock


@dataclass(frozen=True)
class PaddleOcrCandidateConfig:
    enabled: bool = False
    dependency_review_approved: bool = False
    model_license_review_approved: bool = False
    runtime_policy_approved: bool = False

    @property
    def approved(self) -> bool:
        return (
            self.enabled
            and self.dependency_review_approved
            and self.model_license_review_approved
            and self.runtime_policy_approved
        )


@dataclass(frozen=True)
class PaddleOcrCandidateRequest:
    image_handle: str
    page: int | None
    languages: tuple[str, ...]
    timeout_ms: int


@dataclass(frozen=True)
class PaddleOcrCandidateRuntimeResult:
    status: Literal["success", "failed", "timeout"]
    blocks: list[dict[str, object]] | None = None
    stdout: str = ""
    stderr: str = ""
    error_detail: str = ""
    metadata: dict[str, object] | None = None


class PaddleOcrCandidateRuntimePort(Protocol):
    def recognize(self, request: PaddleOcrCandidateRequest) -> PaddleOcrCandidateRuntimeResult: ...


class PaddleOcrCandidateEngine:
    """OcrEnginePort-compatible placeholder that never starts a runtime."""

    engine_id = "paddleocr-candidate-disabled"

    def __init__(
        self,
        config: PaddleOcrCandidateConfig,
        runtime: PaddleOcrCandidateRuntimePort | None = None,
    ) -> None:
        self._config = config
        self._runtime = runtime

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        if self._runtime is None or not self._config.approved:
            return _failure(self.engine_id, "OCR_ENGINE_UNAVAILABLE")
        try:
            runtime_result = self._runtime.recognize(PaddleOcrCandidateRequest(
                image_handle=image.image_handle,
                page=image.page,
                languages=tuple(options.languages),
                timeout_ms=options.timeout_ms,
            ))
        except Exception:
            return _failure(_fake_engine_id(), "OCR_FAILED")
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
    return "paddleocr-candidate-fake"


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


def compose_paddle_ocr_candidate(
    config: PaddleOcrCandidateConfig,
    runtime: PaddleOcrCandidateRuntimePort | None = None,
) -> PaddleOcrCandidateEngine:
    return PaddleOcrCandidateEngine(config, runtime)
