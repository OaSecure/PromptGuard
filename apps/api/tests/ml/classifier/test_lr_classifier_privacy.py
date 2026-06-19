from app.ml.classifier import (
    ClassifierArtifactRef,
    LrClassifierRuntime,
    SegmentClassificationRequest,
    project_classification_result_metadata,
)
from app.ml.segment_embedding import SegmentEmbedding


class FakePredictor:
    target_labels = ["secret", "credential"]

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        return [[0.99, 0.2]]


def test_classifier_metadata_uses_safe_allowlist_without_raw_values():
    result = LrClassifierRuntime(FakePredictor()).classify(
        SegmentClassificationRequest(
            input_id="input-SECRET-RAW-PROMPT",
            segment_embeddings=[
                SegmentEmbedding(
                    segment_id="s1",
                    vector=[0.12345, 0.98765],
                    embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
                    dimension=2,
                    pooling="mean",
                    normalized=True,
                )
            ],
            artifact=ClassifierArtifactRef(
                artifact_id="lr-v205",
                manifest_version="v205",
                runtime_version="lr-runtime-v1",
                target_labels=["secret", "credential"],
                candidate_threshold=0.575,
                embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
            ),
        )
    )

    payload = project_classification_result_metadata(result)
    payload_text = str(payload)

    assert set(payload) == {"candidate_count", "candidates", "failure"}
    assert set(payload["candidates"][0]) == {"segment_id", "label", "score_bucket", "threshold", "artifact_id", "runtime_version"}
    assert "SECRET-RAW-PROMPT" not in payload_text
    assert "0.12345" not in payload_text
    assert "0.98765" not in payload_text
    assert "0.99" not in payload_text
    assert "vector" not in payload_text
    assert "masked_prompt" not in payload_text
    assert "action" not in payload_text
    assert "raw" not in payload_text.lower()
