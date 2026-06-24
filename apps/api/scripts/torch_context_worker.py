"""Metadata-only Torch worker subprocess entry point.

The API process calls this script with the Torch venv Python. This first slice
only establishes the subprocess contract; model execution tasks are added in
the next integration slice.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue  # noqa: E402
from app.runtime.torch_worker_payload import TorchWorkerPayloadStore  # noqa: E402
from app.runtime.torch_worker_protocol import (  # noqa: E402
    build_worker_error,
    dumps_worker_json,
    loads_worker_json,
    validate_worker_request,
)

build_classifier_service_from_manifest = None
project_classification_signal_summary = None
SegmentClassificationRequest = None
QWEN3_EMBEDDING_MODEL = None
AtomEmbeddingModelLoader = None
AtomEmbeddingRequest = None
Qwen3EmbeddingBackend = None
embed_atoms = None
SegmentEmbeddingBuildRequest = None
SegmentEmbeddingPolicy = None
build_segment_embeddings = None
build_verification_request_from_classifier = None
project_verification_signal_summary = None
build_verifier_service_from_manifest = None


class _ContextPipelineRuntime:
    def __init__(
        self,
        *,
        classifier_manifest_path: str,
        verifier_manifest_path: str,
        classifier_bundle: Any,
        verifier_bundle: Any,
        embedding_loader: Any,
        queue: MlInferenceQueue,
        load_generation: int,
    ) -> None:
        self.classifier_manifest_path = classifier_manifest_path
        self.verifier_manifest_path = verifier_manifest_path
        self.classifier_bundle = classifier_bundle
        self.verifier_bundle = verifier_bundle
        self.embedding_loader = embedding_loader
        self.queue = queue
        self.load_generation = load_generation


_CONTEXT_RUNTIME_LOCK = Lock()
_CONTEXT_RUNTIME: _ContextPipelineRuntime | None = None
_CONTEXT_RUNTIME_LOAD_GENERATION = 0


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


def serve() -> int:
    for line in sys.stdin:
        response = _handle_payload(loads_worker_json(line))
        print(dumps_worker_json(response), flush=True)
    return 0


def _handle_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return build_worker_error("TORCH_WORKER_INVALID_REQUEST")
    validation = validate_worker_request(payload)
    task = payload.get("task") if isinstance(payload.get("task"), str) else None
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    if not validation.ok:
        return build_worker_error(validation.error_code or "TORCH_WORKER_INVALID_REQUEST", task=task, request_id=request_id)
    if task == "context_smoke":
        return {"ok": True, "task": task, "request_id": request_id, "metadata": {"worker": "torch"}}
    if task == "context_pipeline":
        return {**_context_pipeline_result(payload, request_id=request_id), "task": task, "request_id": request_id}
    return build_worker_error("TORCH_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)


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

    result = _context_pipeline_result(payload, request_id=request_id)
    print(dumps_worker_json({**result, "task": task, "request_id": request_id}))
    return 0 if result.get("ok") is True else 1


def _context_pipeline_result(payload: dict[str, Any], *, request_id: str | None) -> dict[str, Any]:
    payload_dir = os.getenv("PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR", "").strip()
    metadata = payload.get("metadata", {})
    payload_ref = metadata.get("payload_ref") if isinstance(metadata, dict) else None
    if not payload_dir or not isinstance(payload_ref, str):
        return build_worker_error("TORCH_WORKER_PAYLOAD_UNAVAILABLE", task="context_pipeline", request_id=request_id)
    try:
        worker_payload = TorchWorkerPayloadStore(Path(payload_dir)).read(payload_ref)
    except Exception:
        return build_worker_error("TORCH_WORKER_PAYLOAD_UNAVAILABLE", task="context_pipeline", request_id=request_id)
    return _execute_context_pipeline(worker_payload, request_id=request_id)


def _execute_context_pipeline(worker_payload: dict[str, Any], *, request_id: str | None) -> dict[str, Any]:
    _load_context_pipeline_dependencies()

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

    try:
        runtime = _get_context_pipeline_runtime(
            classifier_manifest_path=classifier_manifest_path,
            verifier_manifest_path=verifier_manifest_path,
        )
    except Exception:
        return build_worker_error("TORCH_WORKER_CONTEXT_MODEL_UNAVAILABLE", task="context_pipeline", request_id=request_id)

    queue = runtime.queue
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
            runtime.embedding_loader,
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
        operation=lambda: runtime.classifier_bundle.service.classify(
            SegmentClassificationRequest(
                input_id=input_id,
                segment_embeddings=segment_embedding_result.segment_embeddings,
                artifact=runtime.classifier_bundle.artifact,
            )
        ),
    )
    if classification_result.status != "succeeded" or classification_result.value.failure is not None:
        return build_worker_error("TORCH_WORKER_CLASSIFIER_FAILED", task="context_pipeline", request_id=request_id)

    verification_request = build_verification_request_from_classifier(
        input_id=input_id,
        classification=classification_result.value,
        artifact=runtime.verifier_bundle.artifact,
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
        operation=lambda: runtime.verifier_bundle.service.verify(verification_request),
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
            "runtime": {
                "load_generation": runtime.load_generation,
                "classifier_cached": True,
                "verifier_cached": True,
                "embedding_loader_cached": True,
            },
            "queue": queue.snapshot().model_dump(),
        },
    }


def _get_context_pipeline_runtime(*, classifier_manifest_path: str, verifier_manifest_path: str) -> _ContextPipelineRuntime:
    global _CONTEXT_RUNTIME
    global _CONTEXT_RUNTIME_LOAD_GENERATION

    with _CONTEXT_RUNTIME_LOCK:
        if (
            _CONTEXT_RUNTIME is not None
            and _CONTEXT_RUNTIME.classifier_manifest_path == classifier_manifest_path
            and _CONTEXT_RUNTIME.verifier_manifest_path == verifier_manifest_path
        ):
            return _CONTEXT_RUNTIME

        if _CONTEXT_RUNTIME is not None:
            _CONTEXT_RUNTIME.queue.shutdown()

        classifier_bundle = build_classifier_service_from_manifest(Path(classifier_manifest_path))
        verifier_bundle = build_verifier_service_from_manifest(Path(verifier_manifest_path))
        embedding_loader = AtomEmbeddingModelLoader(lambda model_name: Qwen3EmbeddingBackend(model_name, trust_remote_code=True))
        _CONTEXT_RUNTIME_LOAD_GENERATION += 1
        _CONTEXT_RUNTIME = _ContextPipelineRuntime(
            classifier_manifest_path=classifier_manifest_path,
            verifier_manifest_path=verifier_manifest_path,
            classifier_bundle=classifier_bundle,
            verifier_bundle=verifier_bundle,
            embedding_loader=embedding_loader,
            queue=MlInferenceQueue(max_workers=1, max_queue_size=1),
            load_generation=_CONTEXT_RUNTIME_LOAD_GENERATION,
        )
        return _CONTEXT_RUNTIME


def _reset_context_pipeline_runtime_for_tests() -> None:
    global _CONTEXT_RUNTIME
    global _CONTEXT_RUNTIME_LOAD_GENERATION

    with _CONTEXT_RUNTIME_LOCK:
        if _CONTEXT_RUNTIME is not None:
            _CONTEXT_RUNTIME.queue.shutdown()
        _CONTEXT_RUNTIME = None
        _CONTEXT_RUNTIME_LOAD_GENERATION = 0


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
    from app.atoms import AnalysisAtom

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
    from app.segmenter import AnalysisSegment

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
    from app.atoms import TextRange

    if isinstance(value, dict):
        return TextRange(start=int(value.get("start", 0)), end=int(value.get("end", len(text))))
    return TextRange(start=0, end=len(text))


def _load_context_pipeline_dependencies() -> None:
    global AtomEmbeddingModelLoader
    global AtomEmbeddingRequest
    global QWEN3_EMBEDDING_MODEL
    global Qwen3EmbeddingBackend
    global SegmentClassificationRequest
    global SegmentEmbeddingBuildRequest
    global SegmentEmbeddingPolicy
    global build_classifier_service_from_manifest
    global build_segment_embeddings
    global build_verification_request_from_classifier
    global build_verifier_service_from_manifest
    global embed_atoms
    global project_classification_signal_summary
    global project_verification_signal_summary

    from app.ml.classifier.factory import build_classifier_service_from_manifest as classifier_factory
    from app.ml.classifier.metadata import project_classification_signal_summary as classification_summary
    from app.ml.classifier.models import SegmentClassificationRequest as ClassificationRequest
    from app.ml.embedding import (
        QWEN3_EMBEDDING_MODEL as qwen3_model,
        AtomEmbeddingModelLoader as EmbeddingModelLoader,
        AtomEmbeddingRequest as EmbeddingRequest,
        Qwen3EmbeddingBackend as EmbeddingBackend,
        embed_atoms as embed_atom_batch,
    )
    from app.ml.segment_embedding import (
        SegmentEmbeddingBuildRequest as SegmentEmbeddingRequest,
        SegmentEmbeddingPolicy as SegmentPolicy,
        build_segment_embeddings as build_segment_embedding_batch,
    )
    from app.ml.verifier import (
        build_verification_request_from_classifier as build_verification_request,
        project_verification_signal_summary as verification_summary,
    )
    from app.ml.verifier.factory import build_verifier_service_from_manifest as verifier_factory

    if build_classifier_service_from_manifest is None:
        build_classifier_service_from_manifest = classifier_factory
    if project_classification_signal_summary is None:
        project_classification_signal_summary = classification_summary
    if SegmentClassificationRequest is None:
        SegmentClassificationRequest = ClassificationRequest
    if QWEN3_EMBEDDING_MODEL is None:
        QWEN3_EMBEDDING_MODEL = qwen3_model
    if AtomEmbeddingModelLoader is None:
        AtomEmbeddingModelLoader = EmbeddingModelLoader
    if AtomEmbeddingRequest is None:
        AtomEmbeddingRequest = EmbeddingRequest
    if Qwen3EmbeddingBackend is None:
        Qwen3EmbeddingBackend = EmbeddingBackend
    if embed_atoms is None:
        embed_atoms = embed_atom_batch
    if SegmentEmbeddingBuildRequest is None:
        SegmentEmbeddingBuildRequest = SegmentEmbeddingRequest
    if SegmentEmbeddingPolicy is None:
        SegmentEmbeddingPolicy = SegmentPolicy
    if build_segment_embeddings is None:
        build_segment_embeddings = build_segment_embedding_batch
    if build_verification_request_from_classifier is None:
        build_verification_request_from_classifier = build_verification_request
    if project_verification_signal_summary is None:
        project_verification_signal_summary = verification_summary
    if build_verifier_service_from_manifest is None:
        build_verifier_service_from_manifest = verifier_factory


if __name__ == "__main__":
    raise SystemExit(serve() if "--serve" in sys.argv[1:] else main())
