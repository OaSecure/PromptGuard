"""Install-free, fail-closed boundary for a possible future PaddleOCR adapter."""

from dataclasses import dataclass

from app.domain.types.common import PipelineFailure
from app.domain.types.parser import OcrImageInput, OcrOptions, OcrResult


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


class PaddleOcrCandidateEngine:
    """Placeholder port implementation that never imports or executes PaddleOCR."""

    engine_id = "paddleocr-candidate-disabled"

    def __init__(self, config: PaddleOcrCandidateConfig) -> None:
        self._config = config

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        del image, options
        code = "OCR_ENGINE_UNAVAILABLE"
        return OcrResult(
            status="failed",
            blocks=[],
            engine_id=self.engine_id,
            failure=PipelineFailure(
                code=code,
                message=code,
                retryable=False,
                module=self.engine_id,
            ),
        )


def compose_paddle_ocr_candidate(config: PaddleOcrCandidateConfig) -> PaddleOcrCandidateEngine:
    """Keep the candidate unavailable even if incomplete approvals are toggled."""

    return PaddleOcrCandidateEngine(config)
