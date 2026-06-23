"""Lazy PaddleOCR runtime boundary for local OCR execution."""

from dataclasses import dataclass
from importlib import import_module as default_import_module
from typing import Callable

from .paddle_runtime import PaddleOcrRuntimeRequest, PaddleOcrRuntimeResult

PaddleOcrFactory = Callable[..., object]
ImageResolver = Callable[[str], object]


@dataclass(frozen=True)
class PaddleOcrLazyRuntimeConfig:
    enabled: bool = True
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
        ocr_factory: PaddleOcrFactory | None = None,
        image_resolver: ImageResolver | None = None,
    ) -> None:
        self._config = config
        self._import_module = import_module
        self._ocr_factory = ocr_factory
        self._image_resolver = image_resolver
        self._ocr: object | None = None

    def recognize(self, request: PaddleOcrRuntimeRequest) -> PaddleOcrRuntimeResult:
        if not self._config.enabled:
            return PaddleOcrRuntimeResult(status="unavailable")
        image = self._resolve_image(request.image_handle)
        if image is None:
            return PaddleOcrRuntimeResult(status="unavailable")
        try:
            ocr = self._get_ocr(request.languages)
        except ModuleNotFoundError:
            return PaddleOcrRuntimeResult(status="unavailable")
        except Exception:
            return PaddleOcrRuntimeResult(status="failed")
        try:
            raw_result = _run_ocr(ocr, image)
        except Exception:
            return PaddleOcrRuntimeResult(status="failed")
        return PaddleOcrRuntimeResult(status="success", blocks=_extract_blocks(raw_result, request.page))

    def _resolve_image(self, image_handle: str) -> object | None:
        if self._image_resolver is None:
            return None
        try:
            return self._image_resolver(image_handle)
        except Exception:
            return None

    def _get_ocr(self, languages: tuple[str, ...]) -> object:
        if self._ocr is None:
            factory = self._ocr_factory
            if factory is None:
                module = self._import_module("paddleocr")
                factory = getattr(module, "PaddleOCR")
            self._ocr = factory(lang=_select_language(languages))
        return self._ocr


def _run_ocr(ocr: object, image: object) -> object:
    predict = getattr(ocr, "predict", None)
    if callable(predict):
        return predict(image)
    legacy_ocr = getattr(ocr, "ocr", None)
    if callable(legacy_ocr):
        return legacy_ocr(image)
    raise RuntimeError("paddle_ocr_method_unavailable")


def _select_language(languages: tuple[str, ...]) -> str:
    normalized = {language.lower() for language in languages}
    if normalized & {"kor", "ko", "korean"}:
        return "korean"
    if normalized & {"eng", "en", "english"}:
        return "en"
    return "korean"


def _extract_blocks(raw_result: object, page: int | None) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    _collect_blocks(raw_result, page, blocks)
    return blocks


def _collect_blocks(value: object, page: int | None, blocks: list[dict[str, object]]) -> None:
    if isinstance(value, dict):
        texts = value.get("rec_texts")
        scores = value.get("rec_scores")
        if isinstance(texts, list):
            for index, text in enumerate(texts):
                score = scores[index] if isinstance(scores, list) and index < len(scores) else None
                _append_block(blocks, text, score, page)
        return

    if isinstance(value, (list, tuple)):
        legacy_text, legacy_score = _legacy_text_and_score(value)
        if legacy_text is not None:
            _append_block(blocks, legacy_text, legacy_score, page)
            return
        for item in value:
            _collect_blocks(item, page, blocks)


def _legacy_text_and_score(value: object) -> tuple[object | None, object | None]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None, None
    runtime = value[1]
    if isinstance(runtime, (list, tuple)) and len(runtime) >= 2:
        return runtime[0], runtime[1]
    return None, None


def _append_block(blocks: list[dict[str, object]], text: object, confidence: object, page: int | None) -> None:
    if not isinstance(text, str) or not text.strip():
        return
    block: dict[str, object] = {"text": text, "confidence": confidence}
    if page is not None:
        block["page"] = page
    blocks.append(block)

