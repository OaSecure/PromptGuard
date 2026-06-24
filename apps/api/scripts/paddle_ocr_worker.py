"""Metadata-only PaddleOCR worker subprocess entry point."""

import os
import sys
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.ocr.paddle_real_adapter import _extract_blocks  # noqa: E402
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue  # noqa: E402
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore, decode_bytes  # noqa: E402
from app.runtime.paddle_worker_protocol import (  # noqa: E402
    build_paddle_worker_error,
    dumps_paddle_worker_json,
    loads_paddle_worker_json,
    validate_paddle_worker_request,
)

PaddleOCR = None


class _PaddleOcrRuntime:
    def __init__(self, *, lang: str, ocr: Any, queue: MlInferenceQueue, load_generation: int) -> None:
        self.lang = lang
        self.ocr = ocr
        self.queue = queue
        self.load_generation = load_generation


_PADDLE_RUNTIME_LOCK = Lock()
_PADDLE_RUNTIMES: dict[str, _PaddleOcrRuntime] = {}
_PADDLE_RUNTIME_LOAD_GENERATION = 0


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
    if task == "ocr_smoke":
        print(dumps_paddle_worker_json({"ok": True, "task": task, "request_id": request_id, "metadata": {"worker": "paddle"}}))
        return 0
    if task != "ocr_image":
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)))
        return 1
    return _run_ocr_image(payload, task=task, request_id=request_id)


def serve() -> int:
    for line in sys.stdin:
        response = _handle_payload(loads_paddle_worker_json(line))
        print(dumps_paddle_worker_json(response), flush=True)
    return 0


def _handle_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return build_paddle_worker_error("PADDLE_WORKER_INVALID_REQUEST")
    validation = validate_paddle_worker_request(payload)
    task = payload.get("task") if isinstance(payload.get("task"), str) else None
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    if not validation.ok:
        return build_paddle_worker_error(validation.error_code or "PADDLE_WORKER_INVALID_REQUEST", task=task, request_id=request_id)
    if task == "ocr_smoke":
        return {"ok": True, "task": task, "request_id": request_id, "metadata": {"worker": "paddle"}}
    if task != "ocr_image":
        return build_paddle_worker_error("PADDLE_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)
    return {**_ocr_image_result(payload, task=task, request_id=request_id), "task": task, "request_id": request_id}


def _run_ocr_image(payload: dict[str, Any], *, task: str, request_id: str | None) -> int:
    payload_dir = os.getenv("PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR", "").strip()
    metadata = payload.get("metadata", {})
    payload_ref = metadata.get("payload_ref") if isinstance(metadata, dict) else None
    if not payload_dir or not isinstance(payload_ref, str):
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_PAYLOAD_UNAVAILABLE", task=task, request_id=request_id)))
        return 1
    try:
        result = _ocr_image_result(payload, task=task, request_id=request_id)
    except Exception:
        print(dumps_paddle_worker_json(build_paddle_worker_error("PADDLE_WORKER_OCR_FAILED", task=task, request_id=request_id)))
        return 1
    print(dumps_paddle_worker_json({**result, "task": task, "request_id": request_id}))
    return 0 if result.get("ok") is True else 1


def _ocr_image_result(payload: dict[str, Any], *, task: str, request_id: str | None) -> dict[str, Any]:
    payload_dir = os.getenv("PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR", "").strip()
    metadata = payload.get("metadata", {})
    payload_ref = metadata.get("payload_ref") if isinstance(metadata, dict) else None
    if not payload_dir or not isinstance(payload_ref, str):
        return build_paddle_worker_error("PADDLE_WORKER_PAYLOAD_UNAVAILABLE", task=task, request_id=request_id)
    try:
        worker_payload = PaddleWorkerPayloadStore(Path(payload_dir)).read(payload_ref)
        with _suppress_native_output():
            return _execute_ocr_image(worker_payload)
    except Exception:
        return build_paddle_worker_error("PADDLE_WORKER_OCR_FAILED", task=task, request_id=request_id)


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
        runtime = _get_paddle_runtime(lang)
        ocr_result = runtime.queue.execute(
            MlInferenceJob(
                job_id=f"paddle:{lang}:{page if page is not None else 'page'}",
                request_id=f"paddle:{page if page is not None else 'image'}",
                task_type="generic",
                metadata={"engine": "paddleocr", "lang": lang},
            ),
            timeout_ms=120_000,
            operation=lambda: _run_ocr(runtime.ocr, image_path.as_posix()),
        )
        if ocr_result.status != "succeeded":
            return build_paddle_worker_error("PADDLE_WORKER_OCR_FAILED", task="ocr_image")
        raw_result = ocr_result.value
        blocks = _extract_blocks(raw_result, page)
        return {
            "ok": True,
            "metadata": {
                "worker": "paddle",
                "blocks": blocks,
                "runtime": {
                    "load_generation": runtime.load_generation,
                    "lang": runtime.lang,
                    "ocr_cached": True,
                },
                "queue": runtime.queue.snapshot().model_dump(),
            },
        }
    finally:
        image_path.unlink(missing_ok=True)


def _get_paddle_runtime(lang: str) -> _PaddleOcrRuntime:
    global _PADDLE_RUNTIME_LOAD_GENERATION

    with _PADDLE_RUNTIME_LOCK:
        runtime = _PADDLE_RUNTIMES.get(lang)
        if runtime is not None:
            return runtime

        ocr_class = _load_paddle_ocr_class()
        _PADDLE_RUNTIME_LOAD_GENERATION += 1
        runtime = _PaddleOcrRuntime(
            lang=lang,
            ocr=ocr_class(lang=lang),
            queue=MlInferenceQueue(max_workers=1, max_queue_size=1),
            load_generation=_PADDLE_RUNTIME_LOAD_GENERATION,
        )
        _PADDLE_RUNTIMES[lang] = runtime
        return runtime


def _load_paddle_ocr_class():
    global PaddleOCR

    if PaddleOCR is None:
        from paddleocr import PaddleOCR as paddle_ocr_class

        PaddleOCR = paddle_ocr_class
    return PaddleOCR


def _reset_paddle_runtime_for_tests() -> None:
    global _PADDLE_RUNTIME_LOAD_GENERATION

    with _PADDLE_RUNTIME_LOCK:
        for runtime in _PADDLE_RUNTIMES.values():
            runtime.queue.shutdown()
        _PADDLE_RUNTIMES.clear()
        _PADDLE_RUNTIME_LOAD_GENERATION = 0


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


@contextmanager
def _suppress_native_output():
    try:
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError):
        with redirect_stdout(tempfile.TemporaryFile(mode="w+")), redirect_stderr(tempfile.TemporaryFile(mode="w+")):
            yield
        return

    saved_stdout = os.dup(stdout_fd)
    saved_stderr = os.dup(stderr_fd)
    try:
        with tempfile.TemporaryFile(mode="w+b") as sink:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), stdout_fd)
            os.dup2(sink.fileno(), stderr_fd)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, stdout_fd)
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stdout)
        os.close(saved_stderr)


if __name__ == "__main__":
    raise SystemExit(serve() if "--serve" in sys.argv[1:] else main())
