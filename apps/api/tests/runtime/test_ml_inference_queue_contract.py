import ast
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from pydantic import ValidationError

from app.runtime.ml_inference_queue import (
    MlInferenceJob,
    MlInferenceQueue,
    MlInferenceQueueResult,
)


def _job(**overrides) -> MlInferenceJob:
    values = {
        "job_id": "job-1",
        "request_id": "request-1",
        "task_type": "classifier",
        "metadata": {"model": "lr", "segment_count": 1},
    }
    values.update(overrides)
    return MlInferenceJob(**values)


def test_ml_inference_queue_invokes_handler_and_returns_result():
    seen: list[MlInferenceJob] = []

    def handler(job: MlInferenceJob) -> dict[str, str]:
        seen.append(job)
        return {"label": "prompt_injection"}

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)

    result = queue.execute(_job(), timeout_ms=100)

    assert result.status == "succeeded"
    assert result.value == {"label": "prompt_injection"}
    assert result.failure_code is None
    assert seen == [_job()]
    queue.shutdown()


def test_ml_inference_queue_accepts_per_job_operation_without_payload_metadata():
    queue = MlInferenceQueue(max_workers=1, max_queue_size=1)

    result = queue.execute(_job(metadata={"model": "lr"}), timeout_ms=100, operation=lambda: {"label": "safe"})

    assert result.status == "succeeded"
    assert result.value == {"label": "safe"}
    queue.shutdown()


def test_ml_inference_queue_snapshot_tracks_safe_success_counters():
    queue = MlInferenceQueue(max_workers=1, max_queue_size=2)

    result = queue.execute(_job(job_id="telemetry-success"), timeout_ms=100, operation=lambda: "ok")
    snapshot = queue.snapshot()

    assert result.status == "succeeded"
    assert snapshot.capacity == 3
    assert snapshot.in_flight_or_queued == 0
    assert snapshot.submitted_total == 1
    assert snapshot.succeeded_total == 1
    assert snapshot.timeout_total == 0
    assert snapshot.failed_total == 0
    assert snapshot.limit_exceeded_total == 0
    queue.shutdown()


def test_ml_inference_job_metadata_allows_only_safe_coarse_fields():
    job = _job(metadata={"model": "lr", "queue": "primary", "segment_count": 2, "timeout_ms": 3000})

    assert job.metadata == {"model": "lr", "queue": "primary", "segment_count": 2, "timeout_ms": 3000}


@pytest.mark.parametrize(
    "field",
    [
        "raw_prompt",
        "file_content",
        "extracted_text",
        "atom_text",
        "segment_text",
        "detected_raw_value",
        "original_filename",
        "filename",
        "embedding",
        "embedding_vector",
        "vector",
        "raw_logits",
        "model_internals",
    ],
)
def test_ml_inference_job_metadata_rejects_sensitive_fields(field: str):
    with pytest.raises(ValidationError):
        _job(metadata={field: "PRIVATE_SENTINEL"})


def test_ml_inference_job_metadata_rejects_sensitive_fields_case_insensitively():
    with pytest.raises(ValidationError):
        _job(metadata={"Raw_Prompt": "PRIVATE_SENTINEL"})


def test_ml_inference_job_rejects_extra_payload_fields():
    with pytest.raises(ValidationError):
        MlInferenceJob(
            job_id="job-1",
            request_id="request-1",
            task_type="classifier",
            metadata={"model": "lr"},
            raw_prompt="PRIVATE_SENTINEL",
        )


def test_timeout_ms_minimum_boundary():
    queue = MlInferenceQueue(handler=lambda job: "ok", max_workers=1, max_queue_size=1)

    assert queue.execute(_job(), timeout_ms=1).status == "succeeded"
    with pytest.raises(ValueError):
        queue.execute(_job(), timeout_ms=0)
    queue.shutdown()


def test_worker_and_queue_size_boundaries():
    with pytest.raises(ValueError):
        MlInferenceQueue(handler=lambda job: "ok", max_workers=0, max_queue_size=1)
    with pytest.raises(ValueError):
        MlInferenceQueue(handler=lambda job: "ok", max_workers=1, max_queue_size=0)


def test_ml_inference_queue_returns_fail_closed_timeout():
    release = Event()

    def handler(job: MlInferenceJob) -> str:
        release.wait(timeout=1)
        return "late"

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)

    result = queue.execute(_job(), timeout_ms=1)
    release.set()

    assert result.status == "timeout"
    assert result.failure_code == "ML_INFERENCE_TIMEOUT"
    assert result.value is None
    assert queue.snapshot().timeout_total == 1
    queue.shutdown()


def test_timeout_releases_capacity_after_worker_finishes():
    release = Event()

    def handler(job: MlInferenceJob) -> str:
        if job.job_id == "slow":
            release.wait(timeout=1)
        return "done"

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)

    first = queue.execute(_job(job_id="slow"), timeout_ms=1)
    release.set()
    second = queue.execute(_job(job_id="after-timeout"), timeout_ms=100)

    assert first.status == "timeout"
    assert second.status == "succeeded"
    assert second.value == "done"
    queue.shutdown()


def test_ml_inference_queue_returns_fail_closed_when_capacity_is_exceeded():
    release = Event()

    def handler(job: MlInferenceJob) -> str:
        release.wait(timeout=1)
        return "done"

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(queue.execute, _job(job_id="first"), 500)
        second = callers.submit(queue.execute, _job(job_id="second"), 500)
        result = queue.execute(_job(job_id="third"), timeout_ms=100)
        release.set()
        first.result()
        second.result()

    assert result.status == "failed"
    assert result.failure_code == "ML_INFERENCE_LIMIT_EXCEEDED"
    assert result.value is None
    assert queue.snapshot().limit_exceeded_total == 1
    queue.shutdown()


def test_ml_inference_queue_returns_sanitized_failure_on_handler_exception():
    def handler(job: MlInferenceJob) -> str:
        raise RuntimeError("PRIVATE_RAW_BACKEND_DETAIL")

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)

    result = queue.execute(_job(), timeout_ms=100)

    assert result.status == "failed"
    assert result.failure_code == "ML_INFERENCE_WORKER_FAILED"
    assert result.value is None
    assert "PRIVATE_RAW_BACKEND_DETAIL" not in str(result.model_dump())
    assert queue.snapshot().failed_total == 1
    queue.shutdown()


def test_ml_inference_queue_logs_only_safe_failure_metadata(caplog):
    def handler(job: MlInferenceJob) -> str:
        raise RuntimeError("PRIVATE_RAW_BACKEND_DETAIL")

    queue = MlInferenceQueue(handler=handler, max_workers=1, max_queue_size=1)

    with caplog.at_level(logging.ERROR, logger="app.runtime.ml_inference_queue"):
        result = queue.execute(_job(job_id="job-safe-log", metadata={"model": "lr"}), timeout_ms=100)

    assert result.failure_code == "ML_INFERENCE_WORKER_FAILED"
    encoded_logs = "\n".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert "PRIVATE_RAW_BACKEND_DETAIL" not in encoded_logs
    assert "raw_prompt" not in encoded_logs
    assert "file_content" not in encoded_logs
    assert "embedding_vector" not in encoded_logs
    assert "job-safe-log" in encoded_logs
    queue.shutdown()


def test_ml_inference_result_shape_has_no_policy_or_raw_content_fields():
    fields = set(MlInferenceQueueResult.model_fields)

    assert fields.isdisjoint(
        {
            "action",
            "recommended_action",
            "reason_code",
            "raw_prompt",
            "file_content",
            "extracted_text",
            "atom_text",
            "embedding",
            "vector",
            "raw_logits",
        }
    )


def test_ml_inference_queue_snapshot_has_no_raw_content_or_model_payload_fields():
    snapshot = MlInferenceQueue(max_workers=1, max_queue_size=1).snapshot()

    fields = set(snapshot.__class__.model_fields)
    assert fields.isdisjoint(
        {
            "raw_prompt",
            "file_content",
            "extracted_text",
            "atom_text",
            "embedding",
            "vector",
            "raw_logits",
            "model_internals",
            "original_filename",
        }
    )
    assert "raw" not in str(snapshot.model_dump()).lower()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ml_inference_queue_does_not_import_concrete_model_libraries():
    path = Path(__file__).parents[2] / "app" / "runtime" / "ml_inference_queue.py"
    imports = _imports(path)
    forbidden = {"torch", "transformers", "joblib", "sklearn", "numpy"}

    assert not {name for name in imports if name.split(".")[0].lower() in forbidden}


def test_ml_inference_queue_does_not_select_model_adapter_directly():
    path = Path(__file__).parents[2] / "app" / "runtime" / "ml_inference_queue.py"
    source = path.read_text(encoding="utf-8").lower()

    assert "create_qwen3_backend" not in source
    assert "load_lr_classifier_service" not in source
    assert "load_roberta_pair_scorer" not in source
