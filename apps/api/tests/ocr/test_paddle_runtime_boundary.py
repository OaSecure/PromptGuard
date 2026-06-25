import logging

from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.paddle_runtime import (
    PaddleOcrRuntimeConfig,
    compose_paddle_ocr_engine,
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


def _recognize(config: PaddleOcrRuntimeConfig):
    return compose_paddle_ocr_engine(config).recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE:/PRIVATE_MODEL_PATH"),
        OcrOptions(languages=["kor", "eng"], timeout_ms=500),
    )


def test_runtime_is_fail_closed_by_default_without_runtime(caplog):
    caplog.set_level(logging.ERROR)

    result = _recognize(PaddleOcrRuntimeConfig())

    assert result.status == "failed"
    assert result.blocks == []
    assert result.engine_id == "paddleocr-runtime"
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert caplog.text == ""


def test_disabled_runtime_config_does_not_activate_runtime():
    result = _recognize(PaddleOcrRuntimeConfig(enabled=False))

    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_runtime_boundary_does_not_expose_private_runtime_values(caplog):
    caplog.set_level(logging.ERROR)

    result = _recognize(PaddleOcrRuntimeConfig(enabled=True))
    serialized = result.model_dump_json() + caplog.text + repr(result)

    assert result.failure is not None
    assert all(value not in serialized for value in SENSITIVE)

