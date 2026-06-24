import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.infrastructure.ocr.paddle_runtime import PaddleOcrRuntimeRequest, PaddleOcrRuntimeResult
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore, encode_bytes
from app.runtime.paddle_worker_protocol import (
    PADDLE_WORKER_PROTOCOL_VERSION,
    dumps_paddle_worker_json,
    loads_paddle_worker_json,
    validate_paddle_worker_request,
)


@dataclass(frozen=True)
class PaddleWorkerClientConfig:
    python_path: Path
    script_path: Path
    timeout_ms: int = 60_000


@dataclass(frozen=True)
class PaddleWorkerRequest:
    task: str
    request_id: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocol_version": PADDLE_WORKER_PROTOCOL_VERSION,
            "task": self.task,
            "request_id": self.request_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PaddleWorkerResult:
    ok: bool
    task: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


Runner = Callable[..., subprocess.CompletedProcess[str]]
ImageResolver = Callable[[str], object]


class PaddleWorkerClient:
    def __init__(
        self,
        config: PaddleWorkerClientConfig,
        *,
        runner: Runner = subprocess.run,
        payload_store: PaddleWorkerPayloadStore | None = None,
    ) -> None:
        self._config = config
        self._runner = runner
        self._payload_store = payload_store

    def execute(self, request: PaddleWorkerRequest, *, payload: dict[str, Any] | None = None) -> PaddleWorkerResult:
        payload_ref: str | None = None
        if payload is not None:
            if self._payload_store is None:
                return _failure("PADDLE_WORKER_PAYLOAD_STORE_UNAVAILABLE", request)
            payload_ref = self._payload_store.write(payload)
            request = PaddleWorkerRequest(
                task=request.task,
                request_id=request.request_id,
                metadata={**request.metadata, "payload_ref": payload_ref},
            )
        control_payload = request.to_payload()
        validation = validate_paddle_worker_request(control_payload)
        if not validation.ok:
            if payload_ref is not None and self._payload_store is not None:
                self._payload_store.delete(payload_ref)
            return _failure(validation.error_code or "PADDLE_WORKER_REQUEST_INVALID", request)
        try:
            return self._execute_control_payload(control_payload, request)
        finally:
            if payload_ref is not None and self._payload_store is not None:
                self._payload_store.delete(payload_ref)

    def _execute_control_payload(self, control_payload: dict[str, Any], request: PaddleWorkerRequest) -> PaddleWorkerResult:
        try:
            completed = self._runner(
                [_path_arg(self._config.python_path), _path_arg(self._config.script_path)],
                input=dumps_paddle_worker_json(control_payload),
                text=True,
                capture_output=True,
                timeout=self._config.timeout_ms / 1000,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failure("PADDLE_WORKER_TIMEOUT", request)
        except Exception:
            return _failure("PADDLE_WORKER_SPAWN_FAILED", request)

        response = loads_paddle_worker_json(getattr(completed, "stdout", "") or "")
        if response is None:
            return _failure("PADDLE_WORKER_INVALID_RESPONSE", request)
        if getattr(completed, "returncode", 1) != 0 or response.get("ok") is not True:
            return _failure(_safe_error_code(response.get("error_code")), request)
        metadata = response.get("metadata", {})
        return PaddleWorkerResult(
            ok=True,
            task=_optional_text(response.get("task")),
            request_id=_optional_text(response.get("request_id")),
            metadata=metadata if isinstance(metadata, dict) else {},
        )


class PaddleOcrSubprocessRuntime:
    """PaddleOCR runtime adapter that executes OCR in the Paddle venv."""

    def __init__(
        self,
        client: PaddleWorkerClient,
        *,
        image_resolver: ImageResolver,
        inference_queue: MlInferenceQueue | None = None,
    ) -> None:
        self._client = client
        self._image_resolver = image_resolver
        self._inference_queue = inference_queue

    def recognize(self, request: PaddleOcrRuntimeRequest) -> PaddleOcrRuntimeResult:
        try:
            image_payload = _build_image_payload(self._image_resolver(request.image_handle))
        except Exception:
            return PaddleOcrRuntimeResult(status="failed")
        worker_request = PaddleWorkerRequest(
            task="ocr_image",
            request_id="ocr-request",
            metadata={"page": request.page, "language_count": len(request.languages)},
        )
        result = self._execute(
            worker_request,
            timeout_ms=request.timeout_ms,
            payload={
                **image_payload,
                "page": request.page,
                "languages": list(request.languages),
            },
        )
        if not result.ok:
            if result.error_code == "PADDLE_WORKER_TIMEOUT":
                return PaddleOcrRuntimeResult(status="timeout")
            if result.error_code in {"PADDLE_WORKER_PAYLOAD_UNAVAILABLE", "PADDLE_WORKER_SPAWN_FAILED"}:
                return PaddleOcrRuntimeResult(status="unavailable")
            return PaddleOcrRuntimeResult(status="failed")
        blocks = result.metadata.get("blocks", [])
        return PaddleOcrRuntimeResult(status="success", blocks=blocks if isinstance(blocks, list) else [])

    def _execute(
        self,
        request: PaddleWorkerRequest,
        *,
        timeout_ms: int,
        payload: dict[str, Any],
    ) -> PaddleWorkerResult:
        if self._inference_queue is None:
            return self._client.execute(request, payload=payload)
        queued = self._inference_queue.execute(
            MlInferenceJob(
                job_id=f"{request.request_id}:paddle-worker",
                request_id=request.request_id,
                task_type="generic",
                metadata={"worker": "paddle"},
            ),
            timeout_ms=timeout_ms,
            operation=lambda: self._client.execute(request, payload=payload),
        )
        if queued.status != "succeeded":
            return _failure(queued.failure_code or "ML_INFERENCE_WORKER_FAILED", request)
        return queued.value


def _build_image_payload(image: object) -> dict[str, Any]:
    if isinstance(image, str):
        return {"image_b64": encode_bytes(Path(image).read_bytes()), "suffix": _suffix_for_path(Path(image))}
    if isinstance(image, Path):
        return {"image_b64": encode_bytes(image.read_bytes()), "suffix": _suffix_for_path(image)}
    return {"image_b64": encode_bytes(_array_to_ppm_bytes(image)), "suffix": ".ppm"}


def _array_to_ppm_bytes(image: object) -> bytes:
    import numpy as np

    array = np.asarray(image)
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError("unsupported image array")
    rgb = array[:, :, :3].astype(np.uint8, copy=False)
    height, width, _channels = rgb.shape
    return b"P6\n" + f"{width} {height}\n255\n".encode("ascii") + rgb.tobytes()


def _suffix_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ppm"} else ".img"


def _failure(error_code: str, request: PaddleWorkerRequest) -> PaddleWorkerResult:
    return PaddleWorkerResult(ok=False, task=request.task, request_id=request.request_id, error_code=error_code)


def _safe_error_code(value: object) -> str:
    if isinstance(value, str) and value.startswith("PADDLE_WORKER_") and value.isupper():
        return value
    return "PADDLE_WORKER_FAILED"


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _path_arg(path: Path) -> str:
    return path.as_posix()
