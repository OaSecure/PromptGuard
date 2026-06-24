import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.runtime.paddle_worker_client import (
    PaddleOcrSubprocessRuntime,
    PaddleWorkerClient,
    PaddleWorkerClientConfig,
    PaddleWorkerRequest,
    PaddleWorkerResult,
)
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore
from app.runtime.paddle_worker_protocol import (
    PADDLE_WORKER_PROTOCOL_VERSION,
    build_paddle_worker_error,
    validate_paddle_worker_request,
)


def test_paddle_worker_request_rejects_raw_text_filename_path_and_url_fields():
    forbidden_payloads = [
        {"task": "ocr_image", "ocr_text": "secret"},
        {"task": "ocr_image", "original_filename": "private.png"},
        {"task": "ocr_image", "path": "/private/path.png"},
        {"task": "ocr_image", "url": "https://private.example/file.png"},
    ]

    for payload in forbidden_payloads:
        result = validate_paddle_worker_request(payload)
        assert result.ok is False
        assert result.error_code == "PADDLE_WORKER_REQUEST_FORBIDDEN_FIELD"


def test_paddle_worker_error_sanitizes_private_detail():
    result = build_paddle_worker_error(
        "PADDLE_WORKER_OCR_FAILED",
        detail="PRIVATE_OCR_TEXT /private/path.png",
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["ok"] is False
    assert result["error_code"] == "PADDLE_WORKER_OCR_FAILED"
    assert "PRIVATE_OCR_TEXT" not in serialized
    assert "/private/path.png" not in serialized


def test_client_invokes_configured_paddle_python_with_metadata_only_payload():
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        request = json.loads(kwargs["input"])
        assert request == {
            "protocol_version": PADDLE_WORKER_PROTOCOL_VERSION,
            "task": "ocr_image",
            "request_id": "req-1",
            "metadata": {"page": 1},
        }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "task": "ocr_image",
                    "request_id": "req-1",
                    "metadata": {"blocks": [{"text": "safe text", "confidence": 0.9}]},
                }
            ),
            stderr="PRIVATE_STDERR_SHOULD_NOT_LEAK",
        )

    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
    )

    result = client.execute(PaddleWorkerRequest(task="ocr_image", request_id="req-1", metadata={"page": 1}))

    assert result == PaddleWorkerResult(
        ok=True,
        task="ocr_image",
        request_id="req-1",
        metadata={"blocks": [{"text": "safe text", "confidence": 0.9}]},
        error_code=None,
    )
    assert calls == [["/opt/venvs/paddle/bin/python", "/app/scripts/paddle_ocr_worker.py"]]


def test_client_payload_ref_keeps_image_bytes_out_of_control_json_and_deletes_payload(tmp_path):
    payload_store = PaddleWorkerPayloadStore(tmp_path)
    seen_payload_ref: str | None = None

    def fake_run(_command, **kwargs):
        nonlocal seen_payload_ref
        request = json.loads(kwargs["input"])
        serialized_control = kwargs["input"]
        assert "PRIVATE_IMAGE_BYTES" not in serialized_control
        assert request["metadata"]["payload_ref"].startswith("pwpl_")
        seen_payload_ref = request["metadata"]["payload_ref"]
        assert payload_store.read(seen_payload_ref)["image_b64"] == "PRIVATE_IMAGE_BYTES"
        assert kwargs["env"]["PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR"] == tmp_path.as_posix()
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "task": "ocr_image", "request_id": "req-1", "metadata": {"blocks": []}}),
            stderr="",
        )

    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
        payload_store=payload_store,
    )

    result = client.execute(
        PaddleWorkerRequest(task="ocr_image", request_id="req-1"),
        payload={"image_b64": "PRIVATE_IMAGE_BYTES"},
    )

    assert result.ok is True
    assert seen_payload_ref is not None
    assert payload_store.exists(seen_payload_ref) is False


def test_client_timeout_is_fail_closed_without_private_values():
    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["/opt/venvs/paddle/bin/python", "PRIVATE_SCRIPT.py"],
            timeout=0.01,
            output="PRIVATE_OUTPUT",
            stderr="PRIVATE_STDERR",
        )

    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=10,
        ),
        runner=timeout_run,
    )

    result = client.execute(PaddleWorkerRequest(task="ocr_image", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == "PADDLE_WORKER_TIMEOUT"
    assert "PRIVATE" not in repr(result)


def test_paddle_ocr_runtime_runs_worker_call_through_shared_queue(tmp_path):
    calls: list[str] = []
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nPRIVATE_IMAGE_BYTES")

    class Client:
        def execute(self, request, *, payload=None):
            calls.append(f"client:{request.task}")
            return PaddleWorkerResult(
                ok=True,
                task=request.task,
                request_id=request.request_id,
                metadata={"blocks": [{"text": "safe text", "confidence": 0.9}]},
            )

    class Queue:
        def execute(self, job, timeout_ms, *, operation=None):
            calls.append(f"queue:{job.task_type}:{timeout_ms}")
            return SimpleNamespace(status="succeeded", value=operation(), failure_code=None)

    runtime = PaddleOcrSubprocessRuntime(Client(), image_resolver=lambda _handle: image_path, inference_queue=Queue())

    result = runtime.recognize(SimpleNamespace(image_handle="opaque-handle", page=1, languages=("eng",), timeout_ms=987))

    assert result.status == "success"
    assert result.blocks == [{"text": "safe text", "confidence": 0.9}]
    assert calls == ["queue:generic:987", "client:ocr_image"]


def test_paddle_ocr_runtime_fails_closed_when_shared_queue_is_full(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nPRIVATE_IMAGE_BYTES")

    class Client:
        def execute(self, request, *, payload=None):
            raise AssertionError("client must not be called when queue is saturated")

    class Queue:
        def execute(self, job, timeout_ms, *, operation=None):
            return SimpleNamespace(status="failed", value=None, failure_code="ML_INFERENCE_LIMIT_EXCEEDED")

    runtime = PaddleOcrSubprocessRuntime(Client(), image_resolver=lambda _handle: image_path, inference_queue=Queue())

    result = runtime.recognize(SimpleNamespace(image_handle="opaque-handle", page=1, languages=("eng",), timeout_ms=987))

    assert result.status == "failed"
    assert "PRIVATE_IMAGE_BYTES" not in repr(result)
