import os
from pathlib import Path

import pytest
from app.atoms import AnalysisAtom, TextRange
from app.ml.classifier.factory import build_classifier_service_from_manifest
from app.ml.classifier.models import SegmentClassificationRequest
from app.ml.embedding import (
    QWEN3_EMBEDDING_MODEL,
    AtomEmbeddingModelLoader,
    AtomEmbeddingRequest,
    Qwen3EmbeddingBackend,
    embed_atoms,
)
from app.ml.segment_embedding import (
    SegmentEmbeddingBuildRequest,
    SegmentEmbeddingPolicy,
    build_segment_embeddings,
)
from app.ml.verifier import build_verification_request_from_classifier
from app.ml.verifier.factory import build_verifier_service_from_manifest
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue
from app.segmenter import AnalysisSegment


@pytest.mark.skipif(os.getenv("RUN_REAL_CONTEXT_MODEL_TESTS") != "1", reason="real context model smoke is opt-in")
def test_real_context_models_run_through_ml_queue_when_artifacts_are_configured():
    artifact_root_env = os.getenv("PROMPTGUARD_TEST_CONTEXT_ARTIFACT_DIR")
    if not artifact_root_env:
        pytest.skip("PROMPTGUARD_TEST_CONTEXT_ARTIFACT_DIR is not configured")

    artifact_root = Path(artifact_root_env)
    manifest_path = artifact_root / "models" / "context_lr_roberta_active_best_f1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("PromptGuard context manifest is not available")

    queue = MlInferenceQueue(max_workers=1, max_queue_size=2)
    try:
        classifier_bundle = build_classifier_service_from_manifest(manifest_path, artifact_root=artifact_root)
        verifier_bundle = build_verifier_service_from_manifest(manifest_path, artifact_root=artifact_root)
        atom = _atom("Credential exposure risk appears in deployment automation notes.")
        segment = _segment(atom)
        loader = AtomEmbeddingModelLoader(lambda model_name: Qwen3EmbeddingBackend(model_name, trust_remote_code=True))

        embedding_result = queue.execute(
            MlInferenceJob(
                job_id="embed-1",
                request_id="input-1",
                task_type="embedding",
                metadata={"model": "qwen3", "atom_count": 1},
            ),
            timeout_ms=120_000,
            operation=lambda: embed_atoms(
                AtomEmbeddingRequest(
                    input_id="input-1",
                    atoms=[atom],
                    model_name=QWEN3_EMBEDDING_MODEL,
                    normalize_vectors=True,
                    timeout_ms=120_000,
                ),
                loader,
            ),
        )
        assert embedding_result.status == "succeeded"
        assert embedding_result.value.failure is None

        segment_embedding_result = build_segment_embeddings(
            SegmentEmbeddingBuildRequest(
                input_id="input-1",
                segments=[segment],
                atom_embeddings=embedding_result.value.embeddings,
                embedding_model_version=embedding_result.value.embedding_model_version,
                policy=SegmentEmbeddingPolicy(),
            )
        )
        assert segment_embedding_result.failure is None

        classification_result = queue.execute(
            MlInferenceJob(
                job_id="classify-1",
                request_id="input-1",
                task_type="classifier",
                metadata={"model": "lr", "segment_count": 1},
            ),
            timeout_ms=30_000,
            operation=lambda: classifier_bundle.service.classify(
                SegmentClassificationRequest(
                    input_id="input-1",
                    segment_embeddings=segment_embedding_result.segment_embeddings,
                    artifact=classifier_bundle.artifact,
                )
            ),
        )
        assert classification_result.status == "succeeded"
        assert classification_result.value.failure is None
        assert classification_result.value.candidates

        verification_request = build_verification_request_from_classifier(
            input_id="input-1",
            classification=classification_result.value,
            artifact=verifier_bundle.artifact,
            timeout_ms=30_000,
            candidate_text_by_segment_id={segment.segment_id: segment.text},
        )
        verification_result = queue.execute(
            MlInferenceJob(
                job_id="verify-1",
                request_id="input-1",
                task_type="verifier",
                metadata={"model": "roberta", "candidate_count": len(verification_request.candidates)},
            ),
            timeout_ms=30_000,
            operation=lambda: verifier_bundle.service.verify(verification_request),
        )

        assert verification_result.status == "succeeded"
        assert verification_result.value.failure is None
        assert verification_result.value.verifications
        assert queue.snapshot().succeeded_total == 3
    finally:
        queue.shutdown()


def _atom(text: str) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id="atom-1",
        input_id="input-1",
        block_id="block-1",
        text=text,
        original_range=TextRange(start=0, end=len(text)),
        location=None,
        atom_type="paragraph",
        ordinal=0,
    )


def _segment(atom: AnalysisAtom) -> AnalysisSegment:
    return AnalysisSegment(
        segment_id="segment-1",
        input_id="input-1",
        atom_ids=[atom.atom_id],
        text=atom.text,
        original_range=atom.original_range,
        locations=[],
        segment_type="single_atom",
        ordinal=0,
    )
