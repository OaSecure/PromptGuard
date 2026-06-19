from app.ml.classifier import ClassifierArtifactRef, LrClassifierRuntime, SegmentClassificationRequest
from app.ml.segment_embedding import SegmentEmbedding


class FakePredictor:
    def __init__(self, scores: list[list[float]]) -> None:
        self.target_labels = ["secret", "credential", "safe"]
        self._scores = scores

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        return self._scores


def segment_embedding(segment_id: str, vector: list[float]) -> SegmentEmbedding:
    return SegmentEmbedding(
        segment_id=segment_id,
        vector=vector,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
        dimension=len(vector),
        pooling="mean",
        normalized=True,
    )


def artifact(threshold: float = 0.575) -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="lr-v205",
        manifest_version="v205",
        runtime_version="lr-runtime-v1",
        target_labels=["secret", "credential", "safe"],
        candidate_threshold=threshold,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
    )


def test_lr_classifier_emits_candidates_at_or_above_threshold():
    result = LrClassifierRuntime(FakePredictor([[0.575, 0.9, 0.574]])).classify(
        SegmentClassificationRequest(
            input_id="input-1",
            segment_embeddings=[segment_embedding("s1", [0.1, 0.2])],
            artifact=artifact(),
        )
    )

    assert result.failure is None
    assert [(item.segment_id, item.label, item.score) for item in result.candidates] == [
        ("s1", "secret", 0.575),
        ("s1", "credential", 0.9),
    ]
    assert result.candidates[0].threshold == 0.575
    assert result.candidates[0].artifact_id == "lr-v205"


def test_lr_classifier_preserves_segment_order_for_representative_multilabel_case():
    result = LrClassifierRuntime(FakePredictor([[0.6, 0.1, 0.8], [0.1, 0.7, 0.2]])).classify(
        SegmentClassificationRequest(
            input_id="input-1",
            segment_embeddings=[
                segment_embedding("s1", [0.1, 0.2]),
                segment_embedding("s2", [0.3, 0.4]),
            ],
            artifact=artifact(),
        )
    )

    assert result.failure is None
    assert [(item.segment_id, item.label) for item in result.candidates] == [
        ("s1", "secret"),
        ("s1", "safe"),
        ("s2", "credential"),
    ]
