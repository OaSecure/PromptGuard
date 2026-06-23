from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.paddle_candidate import (
    PaddleOcrCandidateConfig,
    compose_paddle_ocr_candidate,
)


def _recognize(config: PaddleOcrCandidateConfig):
    return compose_paddle_ocr_candidate(config).recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE"),
        OcrOptions(languages=["kor", "eng"], timeout_ms=500),
    )


def test_candidate_is_fail_closed_by_default_without_execution():
    result = _recognize(PaddleOcrCandidateConfig())
    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_partial_candidate_approvals_cannot_activate_engine():
    result = _recognize(PaddleOcrCandidateConfig(enabled=True, dependency_review_approved=True))
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_candidate_boundary_remains_future_implementation_after_all_review_flags():
    config = PaddleOcrCandidateConfig(
        enabled=True,
        dependency_review_approved=True,
        model_license_review_approved=True,
        runtime_policy_approved=True,
    )
    assert config.approved is True
    result = _recognize(config)
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert "PRIVATE_IMAGE_HANDLE" not in result.model_dump_json()
