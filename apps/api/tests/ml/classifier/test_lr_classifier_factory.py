from pathlib import Path

import pytest

from app.ml.classifier import ClassifierArtifactRef, SegmentClassificationRequest
from app.ml.classifier.factory import ClassifierRuntimeBuildError, build_lr_classifier_runtime
from app.ml.classifier.loader import JoblibLrClassifierLoadError
from app.ml.segment_embedding import SegmentEmbedding


class FakePredictor:
    target_labels = ["secret", "credential"]

    def __init__(self) -> None:
        self.seen_vectors: list[list[float]] | None = None

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        self.seen_vectors = vectors
        return [[0.99, 0.2]]


def artifact() -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="lr-v205",
        manifest_version="v205",
        runtime_version="lr-runtime-v1",
        target_labels=["secret", "credential"],
        candidate_threshold=0.575,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
    )


def request() -> SegmentClassificationRequest:
    return SegmentClassificationRequest(
        input_id="input-1",
        segment_embeddings=[
            SegmentEmbedding(
                segment_id="s1",
                vector=[0.1, 0.2],
                embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
                dimension=2,
                pooling="mean",
                normalized=True,
            )
        ],
        artifact=artifact(),
    )


def test_lr_classifier_factory_builds_runtime_from_artifact_loader():
    predictor = FakePredictor()

    runtime = build_lr_classifier_runtime(Path("model.joblib"), loader=lambda path: predictor)
    result = runtime.classify(request())

    assert predictor.seen_vectors == [[0.1, 0.2]]
    assert result.failure is None
    assert [(candidate.segment_id, candidate.label, candidate.score) for candidate in result.candidates] == [
        ("s1", "secret", 0.99)
    ]


def test_lr_classifier_factory_wraps_loader_failure_without_sensitive_values():
    def failing_loader(path: Path):
        raise JoblibLrClassifierLoadError(
            "CLASSIFIER_ARTIFACT_INVALID_PAYLOAD",
            "classifier artifact is invalid",
            metadata={
                "raw_prompt": "SENSITIVE_PROMPT_SENTINEL",
                "original_filename": "SENSITIVE_FILENAME_SENTINEL",
            },
        )

    with pytest.raises(ClassifierRuntimeBuildError) as exc_info:
        build_lr_classifier_runtime(Path("SENSITIVE_FILENAME_SENTINEL.joblib"), loader=failing_loader)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_RUNTIME_BUILD_FAILED"
    assert exc_info.value.metadata == {"loader_code": "CLASSIFIER_ARTIFACT_INVALID_PAYLOAD"}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
