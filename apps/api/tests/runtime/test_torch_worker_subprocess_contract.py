import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from app.runtime import resident_worker_process
from app.runtime.resident_worker_process import ResidentWorkerProcess
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
from app.services.analyze_torch_worker import AnalyzeTorchWorker

API_ROOT = Path(__file__).resolve().parents[2]
WORKER_SCRIPT = API_ROOT / "scripts" / "torch_context_worker.py"


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


def test_default_client_uses_resident_torch_worker_process(monkeypatch):
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
    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        )
    )

    first = client.execute(TorchWorkerRequest(task="context_smoke", request_id="req-1"))
    second = client.execute(TorchWorkerRequest(task="context_smoke", request_id="req-2"))
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
        "/opt/venvs/torch/bin/python",
        "/app/scripts/torch_context_worker.py",
        "--serve",
    ]
    assert [request["request_id"] for request in processes[0].requests] == ["req-1", "req-2"]


def test_resident_worker_process_rejects_when_queue_is_full():
    worker = ResidentWorkerProcess(
        ["/opt/venvs/torch/bin/python", "/app/scripts/torch_context_worker.py", "--serve"],
        env_factory=lambda: {},
        timeout_seconds=1,
        max_pending_requests=1,
    )
    assert worker._slots.acquire(blocking=False) is True

    try:
        result = worker.request(json.dumps({"ok": True}))
        snapshot = worker.snapshot()
    finally:
        worker._slots.release()
        worker.close()

    assert result is None
    assert snapshot.requests_total == 0
    assert snapshot.failed_total == 1
    assert snapshot.last_failure_code == "WORKER_QUEUE_FULL"


def test_torch_client_maps_resident_queue_full_to_fail_closed_code():
    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
            timeout_ms=500,
        )
    )
    client._resident = SimpleNamespace(
        request=lambda _payload: None,
        snapshot=lambda: SimpleNamespace(last_failure_code="WORKER_QUEUE_FULL"),
    )

    result = client.execute(TorchWorkerRequest(task="context_smoke", request_id="req-1"))

    assert result.ok is False
    assert result.error_code == "TORCH_WORKER_QUEUE_FULL"


def test_torch_worker_readiness_probe_warms_resident_process(monkeypatch):
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
    client = TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path("/opt/venvs/torch/bin/python"),
            script_path=Path("/app/scripts/torch_context_worker.py"),
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
    assert processes[0].requests[0]["task"] == "context_smoke"


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
        assert kwargs["env"]["PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR"] == tmp_path.as_posix()
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


def test_context_worker_payload_ref_failure_does_not_echo_raw_text(tmp_path):
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
    worker_env = {
        **os.environ,
        "PYTHONPATH": str(API_ROOT),
        "PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR": str(tmp_path),
    }
    worker_env.pop("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", None)
    worker_env.pop("PROMPTGUARD_VERIFIER_MANIFEST_PATH", None)

    completed = subprocess.run(
        [sys.executable, str(WORKER_SCRIPT)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        env=worker_env,
    )

    assert completed.returncode == 1
    response = json.loads(completed.stdout)
    assert response == {
        "error_code": "TORCH_WORKER_CONTEXT_CONFIG_UNAVAILABLE",
        "ok": False,
        "request_id": "req-1",
        "task": "context_pipeline",
    }
    assert "PRIVATE_RAW_CONTEXT" not in completed.stdout
    assert "PRIVATE_RAW_CONTEXT" not in completed.stderr


def test_context_pipeline_orchestrates_real_model_steps_with_sanitized_summary(monkeypatch):
    worker = _load_worker_module()
    calls: list[str] = []

    monkeypatch.setenv("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", "/models/context_manifest.json")
    monkeypatch.setenv("PROMPTGUARD_VERIFIER_MANIFEST_PATH", "/models/context_manifest.json")
    monkeypatch.setattr(worker, "build_classifier_service_from_manifest", lambda _path: _bundle("classifier", calls))
    monkeypatch.setattr(worker, "build_verifier_service_from_manifest", lambda _path: _bundle("verifier", calls))
    monkeypatch.setattr(worker, "AtomEmbeddingModelLoader", lambda backend_factory: SimpleNamespace(backend_factory=backend_factory))
    monkeypatch.setattr(worker, "Qwen3EmbeddingBackend", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(worker, "embed_atoms", lambda request, loader: _embedding_result(request, calls))
    monkeypatch.setattr(worker, "build_segment_embeddings", lambda request: _segment_embedding_result(request, calls))

    result = worker._execute_context_pipeline(
        {
            "input_id": "input-1",
            "atoms": [{"atom_id": "atom-1", "block_id": "block-1", "text": "PRIVATE_RAW_CONTEXT", "ordinal": 0}],
            "segments": [{"segment_id": "segment-1", "atom_ids": ["atom-1"], "text": "PRIVATE_RAW_CONTEXT", "ordinal": 0}],
        },
        request_id="req-1",
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["ok"] is True
    assert result["metadata"]["worker"] == "torch"
    assert result["metadata"]["embedding"]["embedding_count"] == 1
    assert result["metadata"]["classification"]["candidate_count"] == 1
    assert result["metadata"]["verification"]["accepted_count"] == 1
    assert result["metadata"]["runtime"] == {
        "load_generation": 1,
        "classifier_cached": True,
        "verifier_cached": True,
        "embedding_loader_cached": True,
    }
    assert calls == ["classifier_builder", "verifier_builder", "embed", "segment_embedding", "classify", "verify"]
    assert "PRIVATE_RAW_CONTEXT" not in serialized
    assert "0.91" not in serialized
    assert "0.42" not in serialized
    worker._reset_context_pipeline_runtime_for_tests()


def test_context_pipeline_reuses_model_runtime_for_same_manifest(monkeypatch):
    worker = _load_worker_module()
    calls: list[str] = []
    loader_count = 0

    def loader_factory(backend_factory):
        nonlocal loader_count
        loader_count += 1
        return SimpleNamespace(backend_factory=backend_factory)

    monkeypatch.setenv("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", "/models/context_manifest.json")
    monkeypatch.setenv("PROMPTGUARD_VERIFIER_MANIFEST_PATH", "/models/context_manifest.json")
    monkeypatch.setattr(worker, "build_classifier_service_from_manifest", lambda _path: _bundle("classifier", calls))
    monkeypatch.setattr(worker, "build_verifier_service_from_manifest", lambda _path: _bundle("verifier", calls))
    monkeypatch.setattr(worker, "AtomEmbeddingModelLoader", loader_factory)
    monkeypatch.setattr(worker, "Qwen3EmbeddingBackend", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(worker, "embed_atoms", lambda request, loader: _embedding_result(request, calls))
    monkeypatch.setattr(worker, "build_segment_embeddings", lambda request: _segment_embedding_result(request, calls))
    payload = {
        "input_id": "input-1",
        "atoms": [{"atom_id": "atom-1", "block_id": "block-1", "text": "PRIVATE_RAW_CONTEXT", "ordinal": 0}],
        "segments": [{"segment_id": "segment-1", "atom_ids": ["atom-1"], "text": "PRIVATE_RAW_CONTEXT", "ordinal": 0}],
    }

    first = worker._execute_context_pipeline(payload, request_id="req-1")
    second = worker._execute_context_pipeline(payload, request_id="req-2")

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["metadata"]["runtime"]["load_generation"] == 1
    assert second["metadata"]["runtime"]["load_generation"] == 1
    assert calls.count("classifier_builder") == 1
    assert calls.count("verifier_builder") == 1
    assert loader_count == 1
    assert calls.count("embed") == 2
    assert calls.count("classify") == 2
    assert calls.count("verify") == 2
    assert second["metadata"]["queue"]["submitted_total"] == 6
    worker._reset_context_pipeline_runtime_for_tests()


def test_analyze_torch_worker_runs_subprocess_calls_through_shared_queue():
    calls: list[str] = []

    class Client:
        def execute(self, request, *, payload=None):
            calls.append(f"client:{request.task}")
            return TorchWorkerResult(
                ok=True,
                task=request.task,
                request_id=request.request_id,
                metadata={"classification": {"has_candidates": True}},
            )

    class Queue:
        def execute(self, job, timeout_ms, *, operation=None):
            calls.append(f"queue:{job.task_type}:{timeout_ms}")
            return SimpleNamespace(status="succeeded", value=operation(), failure_code=None)

    worker = AnalyzeTorchWorker(Client(), inference_queue=Queue(), inference_timeout_ms=1234)

    outcome = worker.evaluate([(0, SimpleNamespace(input_id="input-1", content="runtime text"))])

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert calls == ["queue:classifier:1234", "client:context_pipeline"]


def test_analyze_torch_worker_fails_closed_when_shared_queue_is_full():
    class Client:
        def execute(self, request, *, payload=None):
            raise AssertionError("client must not be called when queue is saturated")

    class Queue:
        def execute(self, job, timeout_ms, *, operation=None):
            return SimpleNamespace(status="failed", value=None, failure_code="ML_INFERENCE_LIMIT_EXCEEDED")

    worker = AnalyzeTorchWorker(Client(), inference_queue=Queue(), inference_timeout_ms=1234)

    outcome = worker.evaluate([(0, SimpleNamespace(input_id="input-1", content="runtime text"))])

    assert outcome.failure is not None
    assert outcome.failure.code == "ML_INFERENCE_LIMIT_EXCEEDED"


def _load_worker_module():
    spec = importlib.util.spec_from_file_location("torch_context_worker_under_test", WORKER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle(kind: str, calls: list[str]):
    from app.ml.classifier.models import (
        ClassifierArtifactRef,
        SegmentClassificationCandidate,
        SegmentClassificationResult,
    )
    from app.ml.verifier.models import RobertaVerificationEvidence, RobertaVerificationResult, VerifierArtifactRef

    calls.append(f"{kind}_builder")
    if kind == "classifier":
        artifact = ClassifierArtifactRef(
            artifact_id="classifier-artifact",
            manifest_version="manifest-v1",
            runtime_version="classifier-runtime-v1",
            target_labels=["credential_risk"],
            candidate_threshold=0.5,
            embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
        )

        class ClassifierService:
            def classify(self, _request):
                calls.append("classify")
                return SegmentClassificationResult(
                    input_id="input-1",
                    candidates=[
                        SegmentClassificationCandidate(
                            segment_id="segment-1",
                            label="credential_risk",
                            score=0.91,
                            threshold=0.5,
                            artifact_id="classifier-artifact",
                            runtime_version="classifier-runtime-v1",
                        )
                    ],
                )

        return SimpleNamespace(service=ClassifierService(), artifact=artifact)

    artifact = VerifierArtifactRef(
        artifact_id="verifier-artifact",
        model_version="verifier-model-v1",
        runtime_version="verifier-runtime-v1",
    )

    class VerifierService:
        def verify(self, _request):
            calls.append("verify")
            return RobertaVerificationResult(
                input_id="input-1",
                verifications=[
                    RobertaVerificationEvidence(
                        segment_id="segment-1",
                        candidate_label="credential_risk",
                        verifier_status="confirmed",
                        accepted=True,
                        confidence=0.91,
                        verifier_model_version="verifier-model-v1",
                    )
                ],
            )

    return SimpleNamespace(service=VerifierService(), artifact=artifact)


def _embedding_result(request, calls: list[str]):
    from app.ml.embedding.models import AtomEmbedding, AtomEmbeddingResult

    calls.append("embed")
    return AtomEmbeddingResult(
        input_id=request.input_id,
        embeddings=[AtomEmbedding(atom_id="atom-1", vector=[0.42, 0.24])],
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
        dimension=2,
        normalized=True,
    )


def _segment_embedding_result(request, calls: list[str]):
    from app.ml.segment_embedding.models import SegmentEmbedding, SegmentEmbeddingBuildResult

    calls.append("segment_embedding")
    return SegmentEmbeddingBuildResult(
        input_id=request.input_id,
        segment_embeddings=[
            SegmentEmbedding(
                segment_id="segment-1",
                vector=[0.42, 0.24],
                embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
                dimension=2,
                pooling="mean",
                normalized=True,
            )
        ],
    )


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
                "metadata": {"worker": "torch"},
            }
        ) + "\n"
