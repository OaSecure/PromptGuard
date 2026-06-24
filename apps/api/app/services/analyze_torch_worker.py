from typing import Any

from app.atoms.models import PipelineFailure
from app.runtime.torch_worker_client import TorchWorkerClient, TorchWorkerRequest
from app.services.analyze_classifier import AnalyzeClassifierOutcome


class AnalyzeTorchWorker:
    def __init__(self, client: TorchWorkerClient) -> None:
        self._client = client

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

            result = self._client.execute(
                TorchWorkerRequest(task="context_pipeline", request_id=input_id),
                payload=_payload_for_text(input_id, content),
            )
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


def build_analyze_torch_worker(client: TorchWorkerClient) -> AnalyzeTorchWorker:
    return AnalyzeTorchWorker(client)


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
