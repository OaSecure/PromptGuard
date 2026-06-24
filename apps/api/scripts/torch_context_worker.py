"""Metadata-only Torch worker subprocess entry point.

The API process calls this script with the Torch venv Python. This first slice
only establishes the subprocess contract; model execution tasks are added in
the next integration slice.
"""

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.atoms import AnalysisAtom, TextRange  # noqa: E402
from app.ml.classifier.factory import build_classifier_service_from_manifest  # noqa: E402
from app.ml.classifier.metadata import project_classification_signal_summary  # noqa: E402
from app.ml.classifier.models import SegmentClassificationRequest  # noqa: E402
from app.ml.embedding import (  # noqa: E402
    QWEN3_EMBEDDING_MODEL,
    AtomEmbeddingModelLoader,
    AtomEmbeddingRequest,
    Qwen3EmbeddingBackend,
    embed_atoms,
)
from app.ml.segment_embedding import (  # noqa: E402
    SegmentEmbeddingBuildRequest,
    SegmentEmbeddingPolicy,
    build_segment_embeddings,
)
from app.ml.verifier import (  # noqa: E402
    build_verification_request_from_classifier,
    project_verification_signal_summary,
)
from app.ml.verifier.factory import build_verifier_service_from_manifest  # noqa: E402
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue  # noqa: E402
from app.runtime.torch_worker_payload import TorchWorkerPayloadStore  # noqa: E402
from app.runtime.torch_worker_protocol import (  # noqa: E402
    build_worker_error,
    dumps_worker_json,
    loads_worker_json,
    validate_worker_request,
)
from app.segmenter import AnalysisSegment  # noqa: E402


def main() -> int:
    payload = loads_worker_json(sys.stdin.read())
    if payload is None:
        print(dumps_worker_json(build_worker_error("TORCH_WORKER_INVALID_REQUEST")))
        return 1
    validation = validate_worker_request(payload)
    task = payload.get("task") if isinstance(payload.get("task"), str) else None
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    if not validation.ok:
        print(dumps_worker_json(build_worker_error(validation.error_code or "TORCH_WORKER_INVALID_REQUEST", task=task, request_id=request_id)))
        return 1
    if task == "context_smoke":
        print(dumps_worker_json({"ok": True, "task": task, "request_id": request_id, "metadata": {"worker": "torch"}}))
        return 0
    if task == "context_pipeline":
        return _run_context_pipeline(payload, task=task, request_id=request_id)
    print(dumps_worker_json(build_worker_error("TORCH_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)))
    return 1


def _run_context_pipeline(payload: dict, *, task: str, request_id: str | None) -> int:
    payload_dir = os.getenv("PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR", "").strip()
    metadata = payload.get("metadata", {})
    payload_ref = metadata.get("payload_ref") if isinstance(metadata, dict) else None
    if not payload_dir or not isinstance(payload_ref, str):
        print(dumps_worker_json(build_worker_error("TORCH_WORKER_PAYLOAD_UNAVAILABLE", task=task, request_id=request_id)))
        return 1
    try:
        worker_payload = TorchWorkerPayloadStore(Path(payload_dir)).read(payload_ref)
    except Exception:
        print(dumps_worker_json(build_worker_error("TORCH_WORKER_PAYLOAD_UNAVAILABLE", task=task, request_id=request_id)))
        return 1

    result = _execute_context_pipeline(worker_payload, request_id=request_id)
    print(dumps_worker_json({**result, "task": task, "request_id": request_id}))
    return 0 if result.get("ok") is True else 1


def _execute_context_pipeline(worker_payload: dict[str, Any], *, request_id: str | None) -> dict[str, Any]:
    classifier_manifest_path = os.getenv("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", "").strip()
    verifier_manifest_path = os.getenv("PROMPTGUARD_VERIFIER_MANIFEST_PATH", "").strip()
    if not classifier_manifest_path or not verifier_manifest_path:
        return build_worker_error("TORCH_WORKER_CONTEXT_CONFIG_UNAVAILABLE", task="context_pipeline", request_id=request_id)

    try:
        input_id = _required_text(worker_payload.get("input_id"), default=request_id or "context-input")
        atoms = [_coerce_atom(item, input_id=input_id) for item in _required_list(worker_payload.get("atoms"))]
        segments = [_coerce_segment(item, input_id=input_id, atoms_by_id={atom.atom_id: atom for atom in atoms}) for item in _required_list(worker_payload.get("segments"))]
    except Exception:
        return build_worker_error("TORCH_WORKER_CONTEXT_PAYLOAD_INVALID", task="context_pipeline", request_id=request_id)

    queue = MlInferenceQueue(max_workers=1, max_queue_size=1)
    try:
        try:
            classifier_bundle = build_classifier_service_from_manifest(Path(classifier_manifest_path))
            verifier_bundle = build_verifier_service_from_manifest(Path(verifier_manifest_path))
        except Exception:
            return build_worker_error("TORCH_WORKER_CONTEXT_MODEL_UNAVAILABLE", task="context_pipeline", request_id=request_id)

        loader = AtomEmbeddingModelLoader(lambda model_name: Qwen3EmbeddingBackend(model_name, trust_remote_code=True))
        embedding_result = queue.execute(
            MlInferenceJob(
                job_id=f"{request_id or input_id}:embed",
                request_id=input_id,
                task_type="embedding",
                metadata={"model": "qwen3", "atom_count": len(atoms)},
            ),
            timeout_ms=120_000,
            operation=lambda: embed_atoms(
                AtomEmbeddingRequest(
                    input_id=input_id,
                    atoms=atoms,
                    model_name=QWEN3_EMBEDDING_MODEL,
                    normalize_vectors=True,
                    timeout_ms=120_000,
                ),
                loader,
            ),
        )
        if embedding_result.status != "succeeded" or embedding_result.value.failure is not None:
            return build_worker_error("TORCH_WORKER_EMBEDDING_FAILED", task="context_pipeline", request_id=request_id)

        segment_embedding_result = build_segment_embeddings(
            SegmentEmbeddingBuildRequest(
                input_id=input_id,
                segments=segments,
                atom_embeddings=embedding_result.value.embeddings,
                embedding_model_version=embedding_result.value.embedding_model_version,
                policy=SegmentEmbeddingPolicy(),
            )
        )
        if segment_embedding_result.failure is not None:
            return build_worker_error("TORCH_WORKER_SEGMENT_EMBEDDING_FAILED", task="context_pipeline", request_id=request_id)

        classification_result = queue.execute(
            MlInferenceJob(
                job_id=f"{request_id or input_id}:classify",
                request_id=input_id,
                task_type="classifier",
                metadata={"model": "lr", "segment_count": len(segments)},
            ),
            timeout_ms=30_000,
            operation=lambda: classifier_bundle.service.classify(
                SegmentClassificationRequest(
                    input_id=input_id,
                    segment_embeddings=segment_embedding_result.segment_embeddings,
                    artifact=classifier_bundle.artifact,
                )
            ),
        )
        if classification_result.status != "succeeded" or classification_result.value.failure is not None:
            return build_worker_error("TORCH_WORKER_CLASSIFIER_FAILED", task="context_pipeline", request_id=request_id)

        verification_request = build_verification_request_from_classifier(
            input_id=input_id,
            classification=classification_result.value,
            artifact=verifier_bundle.artifact,
            timeout_ms=30_000,
            candidate_text_by_segment_id={segment.segment_id: segment.text for segment in segments},
        )
        verification_result = queue.execute(
            MlInferenceJob(
                job_id=f"{request_id or input_id}:verify",
                request_id=input_id,
                task_type="verifier",
                metadata={"model": "roberta", "candidate_count": len(verification_request.candidates)},
            ),
            timeout_ms=30_000,
            operation=lambda: verifier_bundle.service.verify(verification_request),
        )
        if verification_result.status != "succeeded" or verification_result.value.failure is not None:
            return build_worker_error("TORCH_WORKER_VERIFIER_FAILED", task="context_pipeline", request_id=request_id)

        return {
            "ok": True,
            "metadata": {
                "worker": "torch",
                "atom_count": len(atoms),
                "segment_count": len(segments),
                "embedding": embedding_result.value.safe_metadata(),
                "classification": project_classification_signal_summary(classification_result.value),
                "verification": project_verification_signal_summary(verification_result.value),
                "queue": queue.snapshot().model_dump(),
            },
        }
    finally:
        queue.shutdown()


def _required_text(value: Any, *, default: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if default is not None and default.strip():
        return default
    raise ValueError("required text is missing")


def _required_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("required list is missing")
    return value


def _coerce_atom(item: Any, *, input_id: str) -> AnalysisAtom:
    if not isinstance(item, dict):
        raise ValueError("atom must be an object")
    text = _required_text(item.get("text"))
    original_range = _coerce_range(item.get("original_range"), text=text)
    return AnalysisAtom(
        atom_id=_required_text(item.get("atom_id")),
        input_id=_required_text(item.get("input_id"), default=input_id),
        block_id=_required_text(item.get("block_id"), default="block-1"),
        text=text,
        original_range=original_range,
        location=item.get("location"),
        atom_type=item.get("atom_type") if item.get("atom_type") in {"paragraph", "code_block", "table_row", "ocr_line"} else "paragraph",
        ordinal=int(item.get("ordinal", 0)),
    )


def _coerce_segment(item: Any, *, input_id: str, atoms_by_id: dict[str, AnalysisAtom]) -> AnalysisSegment:
    if not isinstance(item, dict):
        raise ValueError("segment must be an object")
    atom_ids = item.get("atom_ids")
    if not isinstance(atom_ids, list) or any(not isinstance(atom_id, str) for atom_id in atom_ids):
        raise ValueError("segment atom_ids must be a string list")
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        text = "\n".join(atoms_by_id[atom_id].text for atom_id in atom_ids if atom_id in atoms_by_id)
    if not text.strip():
        raise ValueError("segment text is missing")
    original_range = _coerce_range(item.get("original_range"), text=text)
    return AnalysisSegment(
        segment_id=_required_text(item.get("segment_id")),
        input_id=_required_text(item.get("input_id"), default=input_id),
        atom_ids=atom_ids,
        text=text,
        original_range=original_range,
        locations=item.get("locations") if isinstance(item.get("locations"), list) else [],
        segment_type=item.get("segment_type") if item.get("segment_type") in {"semantic", "structure", "size_fallback", "single_atom"} else "single_atom",
        ordinal=int(item.get("ordinal", 0)),
    )


def _coerce_range(value: Any, *, text: str) -> TextRange:
    if isinstance(value, dict):
        return TextRange(start=int(value.get("start", 0)), end=int(value.get("end", len(text))))
    return TextRange(start=0, end=len(text))


if __name__ == "__main__":
    raise SystemExit(main())
