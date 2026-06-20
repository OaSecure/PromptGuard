import logging
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import BoundedSemaphore
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

MlInferenceTaskType = Literal["embedding", "classifier", "verifier", "generic"]
MlInferenceStatus = Literal["succeeded", "timeout", "failed"]
SafeMetadataValue = str | int | float | bool | None

_FORBIDDEN_METADATA_KEYS = {
    "raw_prompt",
    "prompt",
    "file_content",
    "extracted_text",
    "atom_text",
    "segment_text",
    "detected_raw_value",
    "raw_value",
    "matched_value",
    "original_filename",
    "filename",
    "file_name",
    "embedding",
    "embeddings",
    "embedding_vector",
    "segment_vector",
    "vector",
    "raw_logits",
    "model_internals",
}


class MlInferenceJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    task_type: MlInferenceTaskType
    metadata: dict[str, SafeMetadataValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_sensitive_metadata(cls, metadata: dict[str, SafeMetadataValue]) -> dict[str, SafeMetadataValue]:
        forbidden = {key for key in metadata if key.lower() in _FORBIDDEN_METADATA_KEYS}
        if forbidden:
            raise ValueError("ml_inference_metadata_contains_sensitive_field")
        return metadata


class MlInferenceQueueResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    status: MlInferenceStatus
    value: Any = None
    failure_code: str | None = None


MlInferenceHandler = Callable[[MlInferenceJob], Any]
MlInferenceOperation = Callable[[], Any]


class MlInferenceQueue:
    def __init__(self, handler: MlInferenceHandler | None = None, max_workers: int = 1, max_queue_size: int = 1) -> None:
        if max_workers < 1 or max_queue_size < 1:
            raise ValueError("worker and queue sizes must be positive")
        self._handler = handler
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ml-inference-worker")
        self._capacity = BoundedSemaphore(max_workers + max_queue_size)

    def execute(
        self,
        job: MlInferenceJob,
        timeout_ms: int,
        *,
        operation: MlInferenceOperation | None = None,
    ) -> MlInferenceQueueResult:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive")
        runner = operation or self._operation_from_handler(job)
        if not self._capacity.acquire(blocking=False):
            return self._failure(job.job_id, "ML_INFERENCE_LIMIT_EXCEEDED")
        try:
            future = self._executor.submit(runner)
        except Exception:
            self._capacity.release()
            logger.error(
                "ML inference worker submission failed",
                extra=_safe_log_extra(job, "ML_INFERENCE_WORKER_FAILED"),
            )
            return self._failure(job.job_id, "ML_INFERENCE_WORKER_FAILED")
        future.add_done_callback(lambda _: self._capacity.release())
        try:
            return MlInferenceQueueResult(job_id=job.job_id, status="succeeded", value=future.result(timeout=timeout_ms / 1000))
        except TimeoutError:
            future.cancel()
            return self._failure(job.job_id, "ML_INFERENCE_TIMEOUT", status="timeout")
        except Exception:
            logger.error(
                "ML inference worker failed",
                extra=_safe_log_extra(job, "ML_INFERENCE_WORKER_FAILED"),
            )
            return self._failure(job.job_id, "ML_INFERENCE_WORKER_FAILED")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _operation_from_handler(self, job: MlInferenceJob) -> MlInferenceOperation:
        if self._handler is None:
            raise ValueError("ml inference operation is required when no default handler is configured")
        return lambda: self._handler(job)

    @staticmethod
    def _failure(job_id: str, code: str, status: MlInferenceStatus = "failed") -> MlInferenceQueueResult:
        return MlInferenceQueueResult(job_id=job_id, status=status, failure_code=code)


def _safe_log_extra(job: MlInferenceJob, failure_code: str) -> Mapping[str, str]:
    return {
        "failure_code": failure_code,
        "job_id": job.job_id,
        "request_id": job.request_id,
        "task_type": job.task_type,
    }
