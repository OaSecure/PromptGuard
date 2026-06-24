import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from app.runtime.torch_worker_client import (
    TorchWorkerClient,
    TorchWorkerClientConfig,
    TorchWorkerRequest,
    TorchWorkerResult,
)
from app.runtime.torch_worker_payload import TorchWorkerPayloadStore
from app.runtime.torch_worker_protocol import (
    TORCH_WORKER_PROTOCOL_VERSION,
    build_worker_error,
    validate_worker_request,
)


def test_worker_request_rejects_raw_text_and_vector_fields():
    forbidden_payloads = [
        {"task": "context_classify", "raw_prompt": "secret"},
        {"task": "context_classify", "segment_text": "secret"},
        {"task": "context_classify", "embedding_vector": [0.1, 0.2]},
        {"task": "context_classify", "logits": [1.0]},
    ]

    for payload in forbidden_payloads:
        result = validate_worker_request(payload)
        assert result.ok is False
        assert result.error_code == "TORCH_WORKER_REQUEST_FORBIDDEN_FIELD"


def test_worker_error_sanitizes_private_detail():
    result = build_worker_error(
        "TORCH_WORKER_MODEL_FAILED",
        detail="PRIVATE_RAW_PROMPT C:/private/model/path",
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["ok"] is False
    assert result["error_code"] == "TORCH_WORKER_MODEL_FAILED"
    assert "PRIVATE_RAW_PROMPT" not in serialized
    assert "C:/private/model/path" not in serialized
    assert "detail" not in result


def test_client_invokes_configured_torch_python_with_metadata_only_payload():
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        request = json.loads(kwargs["input"])
        assert request == {
            "protocol_version": TORCH_WORKER_PROTOCOL_VERSION,
            "task": "context_smoke",
            "request_id": "req-1",
            "metadata": {"segment_count": 1},
        }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "task": "context_smoke",
                    "request_id": "req-1",
                    "metadata": {"candidate_count": 1},
                }
            ),
            stderr="PRIVATE_STDERR_SHOULD_NOT_LEAK",
        )

    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
    )

    result = client.execute(
        TorchWorkerRequest(
            task="context_smoke",
            request_id="req-1",
            metadata={"segment_count": 1},
        )
    )

    assert result == TorchWorkerResult(
        ok=True,
        task="context_smoke",
        request_id="req-1",
        metadata={"candidate_count": 1},
        error_code=None,
    )
    assert calls == [["/opt/venvs/torch/bin/python", "/app/scripts/torch_context_worker.py"]]


def test_client_timeout_is_fail_closed_without_private_values():
    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["/opt/venvs/torch/bin/python", "PRIVATE_SCRIPT.py"],
            timeout=0.01,
            output="PRIVATE_OUTPUT",
            stderr="PRIVATE_STDERR",
        )

    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=10,
        ),
        runner=timeout_run,
    )

    result = client.execute(TorchWorkerRequest(task="context_smoke", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == "TORCH_WORKER_TIMEOUT"
    assert "PRIVATE" not in repr(result)


def test_client_invalid_worker_output_is_fail_closed_without_stdout_leak():
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="PRIVATE_STDOUT_NOT_JSON", stderr="")

    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
    )

    result = client.execute(TorchWorkerRequest(task="context_smoke", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == "TORCH_WORKER_INVALID_RESPONSE"
    assert "PRIVATE_STDOUT_NOT_JSON" not in repr(result)


def test_client_payload_ref_keeps_raw_text_out_of_worker_control_json(tmp_path):
    payload_store = TorchWorkerPayloadStore(tmp_path)
    seen_payload_ref: str | None = None

    def fake_run(_command, **kwargs):
        nonlocal seen_payload_ref
        request = json.loads(kwargs["input"])
        serialized_control = kwargs["input"]
        assert "PRIVATE_RAW_CONTEXT" not in serialized_control
        assert request["metadata"]["payload_ref"].startswith("twpl_")
        seen_payload_ref = request["metadata"]["payload_ref"]
        assert payload_store.read(seen_payload_ref)["atoms"][0]["text"] == "PRIVATE_RAW_CONTEXT"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "task": "context_pipeline",
                    "request_id": "req-1",
                    "metadata": {"candidate_count": 1},
                }
            ),
            stderr="",
        )

    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
        payload_store=payload_store,
    )

    result = client.execute(
        TorchWorkerRequest(task="context_pipeline", request_id="req-1"),
        payload={"atoms": [{"atom_id": "atom-1", "text": "PRIVATE_RAW_CONTEXT"}]},
    )

    assert result.ok is True
    assert seen_payload_ref is not None
    assert payload_store.exists(seen_payload_ref) is False


def test_client_payload_ref_is_deleted_after_worker_failure(tmp_path):
    payload_store = TorchWorkerPayloadStore(tmp_path)
    seen_payload_ref: str | None = None

    def fake_run(_command, **kwargs):
        nonlocal seen_payload_ref
        request = json.loads(kwargs["input"])
        seen_payload_ref = request["metadata"]["payload_ref"]
        return SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"ok": False, "error_code": "TORCH_WORKER_TASK_NOT_IMPLEMENTED"}),
            stderr="PRIVATE_STDERR",
        )

    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        ),
        runner=fake_run,
        payload_store=payload_store,
    )

    result = client.execute(
        TorchWorkerRequest(task="context_pipeline", request_id="req-1"),
        payload={"atoms": [{"atom_id": "atom-1", "text": "PRIVATE_RAW_CONTEXT"}]},
    )

    assert result.ok is False
    assert seen_payload_ref is not None
    assert payload_store.exists(seen_payload_ref) is False
    assert "PRIVATE" not in repr(result)


def test_context_worker_reads_payload_ref_without_echoing_raw_text(tmp_path):
    payload_store = TorchWorkerPayloadStore(tmp_path)
    payload_ref = payload_store.write(
        {
            "input_id": "input-1",
            "atoms": [{"atom_id": "atom-1", "text": "PRIVATE_RAW_CONTEXT"}],
            "segments": [{"segment_id": "segment-1", "atom_ids": ["atom-1"]}],
        }
    )
    request = {
        "protocol_version": TORCH_WORKER_PROTOCOL_VERSION,
        "task": "context_pipeline",
        "request_id": "req-1",
        "metadata": {"payload_ref": payload_ref},
    }

    completed = subprocess.run(
        [sys.executable, "apps/api/scripts/torch_context_worker.py"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "apps/api", "PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR": str(tmp_path)},
    )

    assert completed.returncode == 0
    response = json.loads(completed.stdout)
    assert response == {
        "metadata": {"atom_count": 1, "segment_count": 1, "worker": "torch"},
        "ok": True,
        "request_id": "req-1",
        "task": "context_pipeline",
    }
    assert "PRIVATE_RAW_CONTEXT" not in completed.stdout
    assert "PRIVATE_RAW_CONTEXT" not in completed.stderr
