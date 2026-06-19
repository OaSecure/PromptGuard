import math

import pytest
from pydantic import ValidationError

from app.ml.classifier import ClassifierArtifactRef, LrClassifierRuntime, SegmentClassificationRequest
from app.ml.segment_embedding import SegmentEmbedding


class FakePredictor:
    def __init__(self, scores: list[list[float]], labels: list[str] | None = None, raises: Exception | None = None) -> None:
        self.target_labels = labels or ["secret", "credential"]
        self._scores = scores
        self._raises = raises

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        if self._raises is not None:
            raise self._raises
        return self._scores


def artifact(threshold: float = 0.575, labels: list[str] | None = None) -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="lr-v205",
        manifest_version="v205",
        runtime_version="lr-runtime-v1",
        target_labels=labels or ["secret", "credential"],
        candidate_threshold=threshold,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
    )


def segment_embedding(vector: list[float], dimension: int | None = None) -> SegmentEmbedding:
    return SegmentEmbedding(
        segment_id="s1",
        vector=vector,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
        dimension=dimension if dimension is not None else len(vector),
        pooling="mean",
        normalized=True,
    )


def request(segments: list[SegmentEmbedding], ref: ClassifierArtifactRef | None = None) -> SegmentClassificationRequest:
    return SegmentClassificationRequest(input_id="input-1", segment_embeddings=segments, artifact=ref or artifact())


@pytest.mark.parametrize("threshold", [-0.001, 1.001])
def test_classifier_artifact_rejects_invalid_thresholds(threshold: float):
    with pytest.raises(ValidationError):
        artifact(threshold=threshold)


def test_lr_classifier_empty_segments_returns_empty_result():
    result = LrClassifierRuntime(FakePredictor([])).classify(request([]))

    assert result.input_id == "input-1"
    assert result.candidates == []
    assert result.failure is None


def test_lr_classifier_empty_vector_fails_without_action():
    result = LrClassifierRuntime(FakePredictor([])).classify(request([segment_embedding([])]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_INVALID_SEGMENT_VECTOR"
    assert "action" not in result.failure.metadata


def test_lr_classifier_dimension_mismatch_fails():
    result = LrClassifierRuntime(FakePredictor([])).classify(request([segment_embedding([0.1], dimension=2)]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_INVALID_SEGMENT_VECTOR"


def test_lr_classifier_predictor_label_mismatch_fails():
    result = LrClassifierRuntime(FakePredictor([[0.9]], labels=["secret"])).classify(request([segment_embedding([0.1])]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_LABEL_MISMATCH"


def test_lr_classifier_score_shape_mismatch_fails():
    result = LrClassifierRuntime(FakePredictor([[0.9]])).classify(request([segment_embedding([0.1])]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_SCORE_SHAPE_MISMATCH"


@pytest.mark.parametrize("bad_score", [math.nan, math.inf, -math.inf])
def test_lr_classifier_non_finite_scores_fail(bad_score: float):
    result = LrClassifierRuntime(FakePredictor([[bad_score, 0.1]])).classify(request([segment_embedding([0.1])]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_INVALID_SCORE"


def test_lr_classifier_predictor_exception_fails_closed():
    result = LrClassifierRuntime(FakePredictor([], raises=RuntimeError("raw backend detail"))).classify(request([segment_embedding([0.1])]))

    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_PREDICTOR_FAILED"
    assert "raw backend detail" not in result.failure.message
