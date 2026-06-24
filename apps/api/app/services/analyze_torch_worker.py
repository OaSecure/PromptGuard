from typing import Any

from app.atoms.models import PipelineFailure
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue
from app.runtime.torch_worker_client import TorchWorkerClient, TorchWorkerRequest
from app.services.analyze_classifier import AnalyzeClassifierOutcome


class AnalyzeTorchWorker:
    def __init__(
        self,
        client: TorchWorkerClient,
        *,
        inference_queue: MlInferenceQueue | None = None,
        inference_timeout_ms: int = 30_000,
    ) -> None:
        self._client = client
        self._inference_queue = inference_queue
        self._inference_timeout_ms = inference_timeout_ms

    def evaluate(self, text_inputs: list[tuple[int, Any]]) -> AnalyzeClassifierOutcome:
        has_candidates = False
        verifier_summaries: list[dict[str, Any]] = []
        for _index, item in text_inputs:
            input_id = getattr(item, "input_id", "")
            content = getattr(item, "content", None)
            if not isinstance(input_id, str) or not input_id.strip():
                return _failed("TORCH_WORKER_CONTEXT_PAYLOAD_INVALID")
            if not isinstance(content, str) or not content.strip():
                continue

            request = TorchWorkerRequest(task="context_pipeline", request_id=input_id)
            payload = _payload_for_text(input_id, content)
            result = self._execute(request, payload=payload)
            if not result.ok:
                return _failed(result.error_code or "TORCH_WORKER_CONTEXT_FAILED")

            classification = _metadata_mapping(result.metadata.get("classification"))
            verification = _metadata_mapping(result.metadata.get("verification"))
            has_candidates = has_candidates or bool(classification.get("has_candidates"))
            if verification:
                verifier_summaries.append(dict(verification))

        return AnalyzeClassifierOutcome(
            enabled=True,
            has_candidates=has_candidates,
            verifier_summaries=verifier_summaries,
        )

    def _execute(self, request: TorchWorkerRequest, *, payload: dict[str, Any]):
        if self._inference_queue is None:
            return self._client.execute(request, payload=payload)
        queued = self._inference_queue.execute(
            MlInferenceJob(
                job_id=f"{request.request_id}:torch-worker",
                request_id=request.request_id,
                task_type="classifier",
                metadata={"worker": "torch"},
            ),
            timeout_ms=self._inference_timeout_ms,
            operation=lambda: self._client.execute(request, payload=payload),
        )
        if queued.status != "succeeded":
            return _worker_failure(queued.failure_code or "ML_INFERENCE_WORKER_FAILED", request)
        return queued.value


def build_analyze_torch_worker(
    client: TorchWorkerClient,
    *,
    inference_queue: MlInferenceQueue | None = None,
    inference_timeout_ms: int = 30_000,
) -> AnalyzeTorchWorker:
    return AnalyzeTorchWorker(client, inference_queue=inference_queue, inference_timeout_ms=inference_timeout_ms)


def _payload_for_text(input_id: str, content: str) -> dict[str, Any]:
    return {
        "input_id": input_id,
        "atoms": [
            {
                "atom_id": f"{input_id}:atom-1",
                "block_id": f"{input_id}:block-1",
                "text": content,
                "ordinal": 0,
            }
        ],
        "segments": [
            {
                "segment_id": f"{input_id}:segment-1",
                "atom_ids": [f"{input_id}:atom-1"],
                "text": content,
                "ordinal": 0,
            }
        ],
    }


def _metadata_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _failed(code: str) -> AnalyzeClassifierOutcome:
    return AnalyzeClassifierOutcome(
        enabled=True,
        failure=PipelineFailure(
            code=code,
            message=code,
            metadata={"failure_code": code},
        ),
    )


def _worker_failure(code: str, request: TorchWorkerRequest):
    from app.runtime.torch_worker_client import TorchWorkerResult

    return TorchWorkerResult(ok=False, task=request.task, request_id=request.request_id, error_code=code)
