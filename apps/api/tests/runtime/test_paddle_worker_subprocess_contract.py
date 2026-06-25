import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.runtime import resident_worker_process
from app.runtime.paddle_worker_client import (
    PaddleOcrSubprocessRuntime,
    PaddleWorkerClient,
    PaddleWorkerClientConfig,
    PaddleWorkerRequest,
    PaddleWorkerResult,
)
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore, encode_bytes
from app.runtime.paddle_worker_protocol import (
    PADDLE_WORKER_PROTOCOL_VERSION,
    build_paddle_worker_error,
    validate_paddle_worker_request,
)

API_ROOT = Path(__file__).resolve().parents[2]
WORKER_SCRIPT = API_ROOT / "scripts" / "paddle_ocr_worker.py"


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


def test_paddle_worker_serve_returns_json_error_when_ocr_raises(monkeypatch):
    worker = _load_worker_module()
    monkeypatch.setattr(worker, "_ocr_image_result", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("PRIVATE_TRACEBACK")))
    payload = {
        "protocol_version": PADDLE_WORKER_PROTOCOL_VERSION,
        "task": "ocr_image",
        "request_id": "req-1",
        "metadata": {"payload_ref": "pwpl_missing"},
    }

    response = worker._safe_handle_payload(payload)

    assert response == {
        "ok": False,
        "error_code": "PADDLE_WORKER_OCR_FAILED",
        "task": "ocr_image",
        "request_id": "req-1",
    }
    assert "PRIVATE_TRACEBACK" not in json.dumps(response)


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


def test_default_client_uses_resident_paddle_worker_process(monkeypatch):
    processes = []

    class FakeProcess:
        def __init__(self, command, **kwargs):
            self.command = list(command)
            self.kwargs = kwargs
            self.stdin = _ResidentInput(self)
            self.stdout = _ResidentOutput(self)
            self.returncode = None
            self.requests = []
            processes.append(self)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(resident_worker_process.subprocess, "Popen", FakeProcess)
    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        )
    )

    first = client.execute(PaddleWorkerRequest(task="ocr_image", request_id="req-1", metadata={"page": 1}))
    second = client.execute(PaddleWorkerRequest(task="ocr_image", request_id="req-2", metadata={"page": 2}))
    snapshot = client.status_snapshot()
    client.close()

    assert first.ok is True
    assert second.ok is True
    assert snapshot is not None
    assert snapshot.process_running is True
    assert snapshot.warm is True
    assert snapshot.requests_total == 2
    assert snapshot.succeeded_total == 2
    assert snapshot.in_flight_or_queued == 0
    assert snapshot.last_failure_code is None
    assert len(processes) == 1
    assert processes[0].command == [
        "/opt/venvs/paddle/bin/python",
        "/app/scripts/paddle_ocr_worker.py",
        "--serve",
    ]
    assert [request["request_id"] for request in processes[0].requests] == ["req-1", "req-2"]


def test_paddle_worker_readiness_probe_uses_metadata_only_smoke(monkeypatch):
    processes = []

    class FakeProcess:
        def __init__(self, command, **kwargs):
            self.command = list(command)
            self.kwargs = kwargs
            self.stdin = _ResidentInput(self)
            self.stdout = _ResidentOutput(self)
            self.returncode = None
            self.requests = []
            processes.append(self)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(resident_worker_process.subprocess, "Popen", FakeProcess)
    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        )
    )

    result = client.readiness_probe()
    snapshot = client.status_snapshot()
    client.close()

    assert result.ok is True
    assert snapshot is not None
    assert snapshot.process_running is True
    assert snapshot.warm is True
    assert snapshot.requests_total == 1
    assert processes[0].requests[0]["task"] == "ocr_smoke"


def test_paddle_client_maps_resident_queue_full_to_fail_closed_code():
    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        )
    )
    client._resident = SimpleNamespace(
        request=lambda _payload: None,
        snapshot=lambda: SimpleNamespace(last_failure_code="WORKER_QUEUE_FULL"),
    )

    result = client.execute(PaddleWorkerRequest(task="ocr_smoke", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == "PADDLE_WORKER_QUEUE_FULL"


@pytest.mark.parametrize(
    ("resident_code", "expected"),
    [
        ("WORKER_NO_RESPONSE", "PADDLE_WORKER_NO_RESPONSE"),
        ("WORKER_REQUEST_FAILED", "PADDLE_WORKER_REQUEST_FAILED"),
        ("WORKER_TIMEOUT", "PADDLE_WORKER_TIMEOUT"),
        (None, "PADDLE_WORKER_UNAVAILABLE"),
    ],
)
def test_paddle_client_preserves_resident_failure_code(resident_code, expected):
    client = PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path("/opt/venvs/paddle/bin/python"),
            script_path=Path("/app/scripts/paddle_ocr_worker.py"),
            timeout_ms=500,
        )
    )
    client._resident = SimpleNamespace(
        request=lambda _payload: None,
        snapshot=lambda: SimpleNamespace(last_failure_code=resident_code),
    )

    result = client.execute(PaddleWorkerRequest(task="ocr_smoke", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == expected


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


def test_paddle_worker_reuses_ocr_runtime_for_same_language(monkeypatch):
    worker = _load_worker_module()
    calls: list[str] = []

    class FakePaddleOCR:
        def __init__(self, *, lang):
            calls.append(f"init:{lang}")
            self.lang = lang

        def predict(self, image):
            calls.append(f"predict:{self.lang}:{Path(image).suffix}")
            return {"safe": True}

    monkeypatch.setattr(worker, "PaddleOCR", FakePaddleOCR)
    monkeypatch.setattr(worker, "_extract_blocks", lambda raw_result, page: [{"text": f"safe-{page}", "confidence": 0.9}])
    payload = {
        "image_b64": encode_bytes(b"\x89PNG\r\n\x1a\nSAFE_IMAGE_BYTES"),
        "suffix": ".png",
        "page": 1,
        "languages": ["kor"],
    }

    first = worker._execute_ocr_image(payload)
    second = worker._execute_ocr_image({**payload, "page": 2})

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["metadata"]["runtime"] == {"load_generation": 1, "lang": "korean", "ocr_cached": True}
    assert second["metadata"]["runtime"] == {"load_generation": 1, "lang": "korean", "ocr_cached": True}
    assert calls == ["init:korean", "predict:korean:.png", "predict:korean:.png"]
    assert second["metadata"]["queue"]["submitted_total"] == 2
    worker._reset_paddle_runtime_for_tests()


def test_paddle_worker_ocr_result_suppresses_native_stdout(monkeypatch, tmp_path, capsys):
    worker = _load_worker_module()
    payload_store = PaddleWorkerPayloadStore(tmp_path)

    class NoisyPaddleOCR:
        def __init__(self, *, lang):
            print(f"native model log {lang}")

        def predict(self, image):
            print(f"native predict log {Path(image).suffix}")
            return {"safe": True}

    monkeypatch.setattr(worker, "PaddleOCR", NoisyPaddleOCR)
    monkeypatch.setattr(worker, "_extract_blocks", lambda raw_result, page: [{"text": "safe", "confidence": 0.9}])
    monkeypatch.setenv("PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR", tmp_path.as_posix())
    payload_ref = payload_store.write(
        {
            "image_b64": encode_bytes(b"\x89PNG\r\n\x1a\nSAFE_IMAGE_BYTES"),
            "suffix": ".png",
            "page": 1,
            "languages": ["kor"],
        }
    )

    result = worker._ocr_image_result(
        {"task": "ocr_image", "request_id": "req-1", "metadata": {"payload_ref": payload_ref}},
        task="ocr_image",
        request_id="req-1",
    )

    captured = capsys.readouterr()
    assert result["ok"] is True
    assert result["metadata"]["blocks"] == [{"text": "safe", "confidence": 0.9}]
    assert "native model log" not in captured.out
    assert "native predict log" not in captured.out
    worker._reset_paddle_runtime_for_tests()


class _ResidentInput:
    def __init__(self, process) -> None:
        self.process = process

    def write(self, value: str) -> None:
        self.process.requests.append(json.loads(value))

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _ResidentOutput:
    def __init__(self, process) -> None:
        self.process = process

    def readline(self) -> str:
        request = self.process.requests[-1]
        return json.dumps(
            {
                "ok": True,
                "task": request["task"],
                "request_id": request["request_id"],
                "metadata": {"worker": "paddle", "blocks": []},
            }
        ) + "\n"


def _load_worker_module():
    spec = importlib.util.spec_from_file_location("paddle_ocr_worker_under_test", WORKER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
