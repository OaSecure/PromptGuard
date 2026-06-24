import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.runtime.resident_worker_process import ResidentWorkerProcess, ResidentWorkerSnapshot
from app.runtime.torch_worker_payload import TorchWorkerPayloadStore
from app.runtime.torch_worker_protocol import (
    TORCH_WORKER_PROTOCOL_VERSION,
    dumps_worker_json,
    loads_worker_json,
    validate_worker_request,
)


@dataclass(frozen=True)
class TorchWorkerClientConfig:
    """Configure the Torch worker subprocess boundary.

    The API process owns this configuration, but the heavy Torch imports stay
    behind the configured Python executable so production calls exercise the
    dedicated Torch virtual environment.
    """

    python_path: Path
    script_path: Path
    timeout_ms: int = 3000
    max_queue_size: int = 32


@dataclass(frozen=True)
class TorchWorkerRequest:
    """Represent a metadata-only request sent to the Torch worker.

    Requests intentionally carry only task metadata. Raw prompt text, file
    content, extracted text, vectors, logits, and exact scores are rejected by
    the shared worker protocol before subprocess execution.
    """

    task: str
    request_id: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-serializable protocol payload for this request."""
        return {
            "protocol_version": TORCH_WORKER_PROTOCOL_VERSION,
            "task": self.task,
            "request_id": self.request_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TorchWorkerResult:
    """Represent a sanitized worker result visible to the API process.

    Failures expose stable error codes only. Worker stdout, stderr, paths, and
    exception details are deliberately excluded from this object.
    """

    ok: bool
    task: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


Runner = Callable[..., subprocess.CompletedProcess[str]]


class TorchWorkerClient:
    """Invoke Torch tasks through a resident subprocess owned by the Torch venv."""

    def __init__(
        self,
        config: TorchWorkerClientConfig,
        *,
        runner: Runner = subprocess.run,
        payload_store: TorchWorkerPayloadStore | None = None,
    ) -> None:
        self._config = config
        self._runner = runner
        self._payload_store = payload_store
        self._resident: ResidentWorkerProcess | None = None

    def execute(self, request: TorchWorkerRequest, *, payload: dict[str, Any] | None = None) -> TorchWorkerResult:
        """Run a worker request and fail closed on validation, timeout, or malformed output."""
        payload_ref: str | None = None
        if payload is not None:
            if self._payload_store is None:
                return _failure("TORCH_WORKER_PAYLOAD_STORE_UNAVAILABLE", request)
            payload_ref = self._payload_store.write(payload)
            request = TorchWorkerRequest(
                task=request.task,
                request_id=request.request_id,
                metadata={**request.metadata, "payload_ref": payload_ref},
            )

        control_payload = request.to_payload()
        validation = validate_worker_request(control_payload)
        if not validation.ok:
            if payload_ref is not None and self._payload_store is not None:
                self._payload_store.delete(payload_ref)
            return _failure(validation.error_code or "TORCH_WORKER_REQUEST_INVALID", request)
        try:
            return self._execute_control_payload(control_payload, request)
        finally:
            if payload_ref is not None and self._payload_store is not None:
                self._payload_store.delete(payload_ref)

    def _execute_control_payload(self, control_payload: dict[str, Any], request: TorchWorkerRequest) -> TorchWorkerResult:
        if self._runner is subprocess.run:
            return self._execute_resident_control_payload(control_payload, request)
        try:
            completed = self._runner(
                [_path_arg(self._config.python_path), _path_arg(self._config.script_path)],
                input=dumps_worker_json(control_payload),
                text=True,
                capture_output=True,
                env=self._worker_env(),
                timeout=self._config.timeout_ms / 1000,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failure("TORCH_WORKER_TIMEOUT", request)
        except Exception:
            return _failure("TORCH_WORKER_SPAWN_FAILED", request)

        response = loads_worker_json(getattr(completed, "stdout", "") or "")
        if response is None:
            return _failure("TORCH_WORKER_INVALID_RESPONSE", request)
        if getattr(completed, "returncode", 1) != 0 or response.get("ok") is not True:
            return _failure(_safe_error_code(response.get("error_code")), request)

        metadata = response.get("metadata", {})
        return TorchWorkerResult(
            ok=True,
            task=_optional_text(response.get("task")),
            request_id=_optional_text(response.get("request_id")),
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    def _execute_resident_control_payload(self, control_payload: dict[str, Any], request: TorchWorkerRequest) -> TorchWorkerResult:
        resident = self._resident_process()
        response_text = resident.request(dumps_worker_json(control_payload))
        if response_text is None:
            if resident.snapshot().last_failure_code == "WORKER_QUEUE_FULL":
                return _failure("TORCH_WORKER_QUEUE_FULL", request)
            return _failure("TORCH_WORKER_TIMEOUT", request)
        response = loads_worker_json(response_text or "")
        if response is None:
            return _failure("TORCH_WORKER_INVALID_RESPONSE", request)
        if response.get("ok") is not True:
            return _failure(_safe_error_code(response.get("error_code")), request)
        metadata = response.get("metadata", {})
        return TorchWorkerResult(
            ok=True,
            task=_optional_text(response.get("task")),
            request_id=_optional_text(response.get("request_id")),
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    def close(self) -> None:
        if self._resident is not None:
            self._resident.close()
            self._resident = None

    def status_snapshot(self) -> ResidentWorkerSnapshot | None:
        return self._resident.snapshot() if self._resident is not None else None

    def readiness_probe(self) -> TorchWorkerResult:
        return self.execute(TorchWorkerRequest(task="context_smoke", request_id="torch-readiness"))

    def _resident_process(self) -> ResidentWorkerProcess:
        if self._resident is None:
            self._resident = ResidentWorkerProcess(
                [_path_arg(self._config.python_path), _path_arg(self._config.script_path), "--serve"],
                env_factory=self._worker_env,
                timeout_seconds=self._config.timeout_ms / 1000,
                max_pending_requests=self._config.max_queue_size,
            )
        return self._resident

    def _worker_env(self) -> dict[str, str]:
        """Pass the active payload store directory to the Torch subprocess."""
        env = dict(os.environ)
        if self._payload_store is not None:
            env["PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR"] = self._payload_store.root.as_posix()
        return env


def _failure(error_code: str, request: TorchWorkerRequest) -> TorchWorkerResult:
    return TorchWorkerResult(ok=False, task=request.task, request_id=request.request_id, error_code=error_code)


def _safe_error_code(value: object) -> str:
    if isinstance(value, str) and value.startswith("TORCH_WORKER_") and value.isupper():
        return value
    return "TORCH_WORKER_FAILED"


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _path_arg(path: Path) -> str:
    return path.as_posix()
