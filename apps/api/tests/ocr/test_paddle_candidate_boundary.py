import logging

from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.paddle_candidate import (
    PaddleOcrCandidateConfig,
    compose_paddle_ocr_candidate,
)

SENSITIVE = (
    "PRIVATE_RAW_TEXT",
    "PRIVATE_IMAGE_HANDLE",
    "/PRIVATE_MODEL_PATH",
    "C:\\private\\model",
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_RAW_EXCEPTION",
)


def _recognize(config: PaddleOcrCandidateConfig):
    return compose_paddle_ocr_candidate(config).recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE:/PRIVATE_MODEL_PATH"),
        OcrOptions(languages=["kor", "eng"], timeout_ms=500),
    )


def test_candidate_is_fail_closed_by_default_without_runtime(caplog):
    caplog.set_level(logging.ERROR)

    result = _recognize(PaddleOcrCandidateConfig())

    assert result.status == "failed"
    assert result.blocks == []
    assert result.engine_id == "paddleocr-candidate-disabled"
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert caplog.text == ""


def test_partial_candidate_approvals_cannot_activate_runtime():
    result = _recognize(PaddleOcrCandidateConfig(enabled=True, dependency_review_approved=True))

    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_all_candidate_approvals_still_do_not_execute_runtime_in_this_pr():
    config = PaddleOcrCandidateConfig(
        enabled=True,
        dependency_review_approved=True,
        model_license_review_approved=True,
        runtime_policy_approved=True,
    )

    result = _recognize(config)

    assert config.approved is True
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert result.blocks == []


def test_candidate_boundary_does_not_expose_private_runtime_values(caplog):
    caplog.set_level(logging.ERROR)

    result = _recognize(PaddleOcrCandidateConfig(enabled=True))
    serialized = result.model_dump_json() + caplog.text + repr(result)

    assert result.failure is not None
    assert all(value not in serialized for value in SENSITIVE)
