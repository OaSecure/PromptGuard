import logging
from typing import Any

from app.atoms.models import PipelineFailure
from app.domain.types.policy import build_context_risk_evidence
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue
from app.runtime.torch_worker_client import TorchWorkerClient, TorchWorkerRequest
from app.services.analyze_classifier import AnalyzeClassifierOutcome

logger = logging.getLogger(__name__)


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
        logger.info(
            "analyze.torch_worker.evaluate_started text_input_count=%s",
            len(text_inputs),
            extra={"text_input_count": len(text_inputs)},
        )
        has_candidates = False
        classification_summaries: list[dict[str, Any]] = []
        verifier_summaries: list[dict[str, Any]] = []
        for _index, item in text_inputs:
            result = self._evaluate_item(item)
            if result is None:
                continue
            if isinstance(result, AnalyzeClassifierOutcome):
                return result
            classification, verification = result
            has_candidates = has_candidates or bool(classification.get("has_candidates"))
            if classification:
                classification_summaries.append(dict(classification))
            if verification:
                verifier_summaries.append(dict(verification))

        context_risk = build_context_risk_evidence(
            enabled=True,
            classification_summaries=classification_summaries,
            verifier_summaries=verifier_summaries,
        )
        logger.info(
            "analyze.torch_worker.evaluate_completed status=%s candidates=%s accepted=%s failure_code=%s",
            context_risk.status,
            context_risk.candidate_count,
            context_risk.accepted_count,
            context_risk.failure_code or "none",
            extra={
                "context_risk_status": context_risk.status,
                "context_risk_candidate_count": context_risk.candidate_count,
                "context_risk_accepted_count": context_risk.accepted_count,
                "context_risk_failure_code": context_risk.failure_code,
            },
        )
        return AnalyzeClassifierOutcome(
            enabled=True,
            has_candidates=has_candidates or context_risk.candidate_count > 0,
            verifier_summaries=verifier_summaries,
            context_risk=context_risk,
        )

    def _evaluate_item(self, item: Any) -> tuple[dict[str, Any], dict[str, Any]] | AnalyzeClassifierOutcome | None:
        input_id = getattr(item, "input_id", "")
        content = getattr(item, "content", None)
        if not _is_non_empty_string(input_id):
            return _failed("TORCH_WORKER_CONTEXT_PAYLOAD_INVALID")
        if not _is_non_empty_string(content):
            return None

        input_id_text = str(input_id)
        content_text = str(content)
        request = TorchWorkerRequest(task="context_pipeline", request_id=input_id_text)
        result = self._execute(request, payload=_payload_for_text(input_id_text, content_text))
        if not result.ok:
            _log_item_failure(result, request)
            return _failed(result.error_code or "TORCH_WORKER_CONTEXT_FAILED")
        _log_item_success(result, request)
        return (
            _metadata_mapping(result.metadata.get("classification")),
            _metadata_mapping(result.metadata.get("verification")),
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
            logger.warning(
                "analyze.torch_worker.queue_failed status=%s failure_code=%s",
                queued.status,
                queued.failure_code or "ML_INFERENCE_WORKER_FAILED",
                extra={
                    "queue_status": queued.status,
                    "context_risk_failure_code": queued.failure_code or "ML_INFERENCE_WORKER_FAILED",
                    "task_type": "classifier",
                },
            )
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


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _log_item_failure(result: Any, request: TorchWorkerRequest) -> None:
    logger.warning(
        "analyze.torch_worker.item_failed task=%s error_code=%s",
        result.task or request.task,
        result.error_code or "TORCH_WORKER_CONTEXT_FAILED",
        extra={
            "task": result.task or request.task,
            "context_risk_failure_code": result.error_code or "TORCH_WORKER_CONTEXT_FAILED",
        },
    )


def _log_item_success(result: Any, request: TorchWorkerRequest) -> None:
    logger.info(
        "analyze.torch_worker.item_succeeded task=%s",
        result.task or request.task,
        extra={"task": result.task or request.task},
    )


def _failed(code: str) -> AnalyzeClassifierOutcome:
    return AnalyzeClassifierOutcome(
        enabled=True,
        failure=PipelineFailure(
            code=code,
            message=code,
            metadata={"failure_code": code},
        ),
        context_risk=build_context_risk_evidence(enabled=True, failure_code=code),
    )


def _worker_failure(code: str, request: TorchWorkerRequest):
    from app.runtime.torch_worker_client import TorchWorkerResult

    return TorchWorkerResult(ok=False, task=request.task, request_id=request.request_id, error_code=code)
