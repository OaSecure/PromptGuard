import logging

from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.paddle_runtime import (
    PaddleOcrRuntimeConfig,
    PaddleOcrRuntimeResult,
    compose_paddle_ocr_engine,
)

SENSITIVE = (
    "PRIVATE_IMAGE_HANDLE",
    "private-file.png",
    "/PRIVATE_MODEL_PATH",
    "C:\\private\\model",
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_RAW_EXCEPTION",
)


class FakeRuntime:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests = []

    def recognize(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result or PaddleOcrRuntimeResult(
            status="success",
            blocks=[
                {
                    "text": "synthetic safe text",
                    "confidence": 0.91,
                    "page": 2,
                    "stdout": "PRIVATE_STDOUT",
                    "model_path": "/PRIVATE_MODEL_PATH",
                }
            ],
            stdout="PRIVATE_STDOUT",
            stderr="PRIVATE_STDERR",
            metadata={"image_handle": "PRIVATE_IMAGE_HANDLE"},
        )


def _config() -> PaddleOcrRuntimeConfig:
    return PaddleOcrRuntimeConfig(enabled=True)


def _recognize(runtime=None):
    return compose_paddle_ocr_engine(_config(), runtime=runtime).recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE/private-file.png", page=2),
        OcrOptions(languages=["kor", "eng"], timeout_ms=500),
    )


def _serialized(result, caplog) -> str:
    return result.model_dump_json() + repr(result) + caplog.text


def test_no_runtime_remains_fail_closed():
    result = _recognize()

    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_fake_runtime_request_is_bounded_and_success_maps_to_ocr_result(caplog):
    caplog.set_level(logging.ERROR)
    runtime = FakeRuntime()

    result = _recognize(runtime)

    assert len(runtime.requests) == 1
    request = runtime.requests[0]
    assert request.page == 2
    assert request.languages == ("kor", "eng")
    assert request.timeout_ms == 500
    assert request.image_handle == "PRIVATE_IMAGE_HANDLE/private-file.png"
    assert result.status == "text_found"
    assert result.failure is None
    assert result.engine_id == "paddleocr-runtime"
    assert [(block.text, block.confidence_bucket, block.location.page) for block in result.blocks] == [
        ("synthetic safe text", "high", 2)
    ]
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_fake_empty_success_maps_to_no_text_detected():
    runtime = FakeRuntime(PaddleOcrRuntimeResult(status="success", blocks=[]))

    result = _recognize(runtime)

    assert result.status == "no_text_detected"
    assert result.blocks == []
    assert result.failure is None


def test_fake_runtime_failure_is_sanitized(caplog):
    caplog.set_level(logging.ERROR)
    runtime = FakeRuntime(PaddleOcrRuntimeResult(
        status="failed",
        blocks=[{"text": "synthetic safe text"}],
        stdout="PRIVATE_STDOUT",
        stderr="PRIVATE_STDERR",
        error_detail="PRIVATE_RAW_EXCEPTION /PRIVATE_MODEL_PATH",
    ))

    result = _recognize(runtime)

    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_fake_runtime_timeout_is_sanitized(caplog):
    caplog.set_level(logging.ERROR)
    runtime = FakeRuntime(PaddleOcrRuntimeResult(
        status="timeout",
        stdout="PRIVATE_STDOUT",
        stderr="PRIVATE_STDERR",
        error_detail="PRIVATE_RAW_EXCEPTION",
    ))

    result = _recognize(runtime)

    assert result.status == "timeout"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_TIMEOUT"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_fake_runtime_exception_is_sanitized(caplog):
    caplog.set_level(logging.ERROR)
    runtime = FakeRuntime(error=RuntimeError("PRIVATE_RAW_EXCEPTION C:\\private\\model"))

    result = _recognize(runtime)

    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)

