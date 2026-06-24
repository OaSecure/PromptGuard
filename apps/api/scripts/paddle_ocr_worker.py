"""Metadata-only PaddleOCR worker subprocess entry point."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.ocr.paddle_real_adapter import _extract_blocks  # noqa: E402
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore, decode_bytes  # noqa: E402
from app.runtime.paddle_worker_protocol import (  # noqa: E402
    build_paddle_worker_error,
    dumps_paddle_worker_json,
    loads_paddle_worker_json,
    validate_paddle_worker_request,
)


def main() -> int:
    payload = loads_paddle_worker_json(sys.stdin.read())
    if payload is None:
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_INVALID_REQUEST")))
        return 1
    validation = validate_paddle_worker_request(payload)
    task = payload.get("task") if isinstance(payload.get("task"), str) else None
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    if not validation.ok:
        print(dumps_paddle_worker_json(
            build_paddle_worker_error(validation.error_code or "PADDLE_WORKER_INVALID_REQUEST", task=task, request_id=request_id)
        ))
        return 1
    if task != "ocr_image":
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)))
        return 1
    return _run_ocr_image(payload, task=task, request_id=request_id)


def _run_ocr_image(payload: dict[str, Any], *, task: str, request_id: str | None) -> int:
    payload_dir = os.getenv("PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR", "").strip()
    metadata = payload.get("metadata", {})
    payload_ref = metadata.get("payload_ref") if isinstance(metadata, dict) else None
    if not payload_dir or not isinstance(payload_ref, str):
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_PAYLOAD_UNAVAILABLE", task=task, request_id=request_id)))
        return 1
    try:
        worker_payload = PaddleWorkerPayloadStore(Path(payload_dir)).read(payload_ref)
        result = _execute_ocr_image(worker_payload)
    except Exception:
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_OCR_FAILED", task=task, request_id=request_id)))
        return 1
    print(dumps_paddle_worker_json({**result, "task": task, "request_id": request_id}))
    return 0 if result.get("ok") is True else 1


def _execute_ocr_image(worker_payload: dict[str, Any]) -> dict[str, Any]:
    image_bytes = decode_bytes(worker_payload.get("image_b64"))
    suffix = worker_payload.get("suffix") if isinstance(worker_payload.get("suffix"), str) else ".img"
    page = worker_payload.get("page") if isinstance(worker_payload.get("page"), int) else None
    languages = worker_payload.get("languages") if isinstance(worker_payload.get("languages"), list) else []
    lang = _select_language(tuple(language for language in languages if isinstance(language, str)))
    with tempfile.NamedTemporaryFile(prefix="promptguard_paddle_", suffix=suffix, delete=False) as handle:
        handle.write(image_bytes)
        image_path = Path(handle.name)
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(lang=lang)
        raw_result = _run_ocr(ocr, image_path.as_posix())
        blocks = _extract_blocks(raw_result, page)
        return {"ok": True, "metadata": {"worker": "paddle", "blocks": blocks}}
    finally:
        image_path.unlink(missing_ok=True)


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


if __name__ == "__main__":
    raise SystemExit(main())
