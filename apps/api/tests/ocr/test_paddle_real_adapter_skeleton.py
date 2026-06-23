import ast
import logging
import os
from pathlib import Path

import pytest
from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.paddle_candidate import (
    PaddleOcrCandidateConfig,
    compose_paddle_ocr_candidate,
)
from app.infrastructure.ocr.paddle_real_adapter import (
    PaddleOcrLazyRuntimeConfig,
    PaddleOcrLazyRuntimeSkeleton,
)

API = Path(__file__).parents[2]
ADAPTER = API / "app" / "infrastructure" / "ocr" / "paddle_real_adapter.py"
FORBIDDEN_IMPORTS = {"paddleocr", "paddle", "paddlepaddle", "paddlex"}
SENSITIVE = (
    "PRIVATE_IMAGE_HANDLE",
    "private-file.png",
    "/PRIVATE_MODEL_PATH",
    "C:\\private\\model",
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_RAW_EXCEPTION",
)


class ImportHook:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def __call__(self, module_name: str):
        self.calls.append(module_name)
        if self.error is not None:
            raise self.error
        return object()


def _approved_config() -> PaddleOcrCandidateConfig:
    return PaddleOcrCandidateConfig(
        enabled=True,
        dependency_review_approved=True,
        model_license_review_approved=True,
        runtime_policy_approved=True,
    )


def _request_result(runtime):
    return compose_paddle_ocr_candidate(_approved_config(), runtime=runtime).recognize(
        OcrImageInput(image_handle="PRIVATE_IMAGE_HANDLE/private-file.png", page=1),
        OcrOptions(languages=["kor"], timeout_ms=500),
    )


def _serialized(result, caplog) -> str:
    return result.model_dump_json() + repr(result) + caplog.text


def test_module_has_no_concrete_paddle_imports():
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imports.isdisjoint(FORBIDDEN_IMPORTS)


def test_lazy_import_is_only_attempted_inside_runtime_recognize():
    hook = ImportHook()
    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        import_module=hook,
        image_resolver=lambda handle: "IMAGE_BYTES_OR_PATH",
    )

    assert hook.calls == []
    _request_result(runtime)
    assert hook.calls == ["paddleocr"]


def test_opt_in_guard_disabled_returns_sanitized_unavailable_without_import(caplog):
    caplog.set_level(logging.ERROR)
    hook = ImportHook()
    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(
            manual_opt_in=False,
            model_directory="/PRIVATE_MODEL_PATH",
        ),
        import_module=hook,
    )

    result = _request_result(runtime)

    assert hook.calls == []
    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_dependency_import_failure_returns_sanitized_unavailable(caplog):
    caplog.set_level(logging.ERROR)
    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(
            manual_opt_in=True,
            model_directory="/PRIVATE_MODEL_PATH",
        ),
        import_module=ImportHook(ModuleNotFoundError("PRIVATE_RAW_EXCEPTION /PRIVATE_MODEL_PATH")),
    )

    result = _request_result(runtime)

    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_constructor_or_runtime_exception_returns_sanitized_failure(caplog):
    caplog.set_level(logging.ERROR)
    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        import_module=ImportHook(RuntimeError("PRIVATE_RAW_EXCEPTION C:\\private\\model")),
        image_resolver=lambda handle: "IMAGE_BYTES_OR_PATH",
    )

    result = _request_result(runtime)

    assert result.status == "failed"
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_local_only_config_shape_has_no_remote_fetch_fields():
    config = PaddleOcrLazyRuntimeConfig(
        manual_opt_in=True,
        model_directory="/PRIVATE_MODEL_PATH",
        allow_remote_fetch=True,
        allow_automatic_download=True,
    )

    assert config.manual_opt_in is True
    assert config.model_directory == "/PRIVATE_MODEL_PATH"
    assert config.allow_remote_fetch is False
    assert config.allow_automatic_download is False
    assert set(type(config).__dataclass_fields__).isdisjoint(
        {"url", "source_url", "model_url", "download_url", "remote_source"}
    )


def test_opt_in_runtime_maps_paddle_ocr_output_to_safe_blocks(caplog):
    caplog.set_level(logging.ERROR)

    class FakePaddleOcr:
        def ocr(self, image):
            assert image == "IMAGE_BYTES_OR_PATH"
            return [[[[0, 0], [1, 0], [1, 1], [0, 1]], ("synthetic safe text", 0.93)]]

    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        ocr_factory=lambda **kwargs: FakePaddleOcr(),
        image_resolver=lambda handle: "IMAGE_BYTES_OR_PATH",
    )

    result = _request_result(runtime)

    assert result.status == "text_found"
    assert result.failure is None
    assert [(block.text, block.confidence_bucket, block.location.page) for block in result.blocks] == [
        ("synthetic safe text", "high", 1)
    ]
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_opt_in_runtime_maps_paddle_ocr_v3_dict_output_to_safe_blocks(caplog):
    caplog.set_level(logging.ERROR)

    class FakePaddleOcr:
        def predict(self, image):
            assert image == "IMAGE_BYTES_OR_PATH"
            return [{"rec_texts": ["synthetic safe text"], "rec_scores": [0.73]}]

    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        ocr_factory=lambda **kwargs: FakePaddleOcr(),
        image_resolver=lambda handle: "IMAGE_BYTES_OR_PATH",
    )

    result = _request_result(runtime)

    assert result.status == "text_found"
    assert result.failure is None
    assert [(block.text, block.confidence_bucket, block.location.page) for block in result.blocks] == [
        ("synthetic safe text", "medium", 1)
    ]
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


def test_opt_in_runtime_returns_no_text_for_empty_paddle_output():
    class FakePaddleOcr:
        def predict(self, image):
            return [{"rec_texts": [], "rec_scores": []}]

    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        ocr_factory=lambda **kwargs: FakePaddleOcr(),
        image_resolver=lambda handle: "IMAGE_BYTES_OR_PATH",
    )

    result = _request_result(runtime)

    assert result.status == "no_text_detected"
    assert result.blocks == []
    assert result.failure is None


def test_opt_in_runtime_without_image_resolver_remains_unavailable(caplog):
    caplog.set_level(logging.ERROR)

    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        ocr_factory=lambda **kwargs: object(),
    )

    result = _request_result(runtime)

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert all(secret not in _serialized(result, caplog) for secret in SENSITIVE)


@pytest.mark.skipif(os.getenv("RUN_REAL_PADDLE_OCR_TESTS") != "1", reason="real PaddleOCR smoke is opt-in")
def test_real_paddle_ocr_runtime_smoke_on_generated_image(tmp_path):
    from PIL import Image, ImageDraw

    image_path = tmp_path / "ocr-smoke.png"
    image = Image.new("RGB", (420, 120), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 42), "PromptGuard OCR smoke", fill="black")
    image.save(image_path)

    runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(manual_opt_in=True),
        image_resolver=lambda handle: handle,
    )

    result = compose_paddle_ocr_candidate(_approved_config(), runtime=runtime).recognize(
        OcrImageInput(image_handle=str(image_path), page=1),
        OcrOptions(languages=["eng"], timeout_ms=60_000),
    )

    assert result.failure is None
    assert result.status in {"text_found", "no_text_detected"}
