import joblib
import pytest

from app.ml.classifier.loader import JoblibLrClassifierLoadError, load_joblib_lr_predictor


class FakeProbabilityClassifier:
    def __init__(self, scores: list[list[float]]) -> None:
        self._scores = scores
        self.seen_vectors: list[list[float]] | None = None

    def predict_proba(self, vectors: list[list[float]]) -> list[list[float]]:
        self.seen_vectors = vectors
        return self._scores


def dump_payload(tmp_path, payload: object):
    artifact_path = tmp_path / "classifier.joblib"
    joblib.dump(payload, artifact_path)
    return artifact_path


def test_joblib_lr_predictor_loads_serialized_payload(tmp_path):
    classifier = FakeProbabilityClassifier([[0.1, 0.9], [0.8, 0.2]])
    artifact_path = dump_payload(
        tmp_path,
        {
            "classifier": classifier,
            "target_labels": ["SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"],
            "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        },
    )

    predictor = load_joblib_lr_predictor(artifact_path)

    assert predictor.target_labels == ["SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"]
    assert predictor.embedding_model_version == "Qwen/Qwen3-Embedding-0.6B"
    assert predictor.predict_probabilities([[0.1, 0.2], [0.3, 0.4]]) == [[0.1, 0.9], [0.8, 0.2]]


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (["not", "a", "dict"], "CLASSIFIER_ARTIFACT_INVALID_PAYLOAD"),
        ({"target_labels": ["SECRET_CREDENTIAL_CONTEXT"]}, "CLASSIFIER_ARTIFACT_MISSING_CLASSIFIER"),
        ({"classifier": object(), "target_labels": ["SECRET_CREDENTIAL_CONTEXT"]}, "CLASSIFIER_ARTIFACT_INVALID_CLASSIFIER"),
        ({"classifier": FakeProbabilityClassifier([[0.1]]), "target_labels": []}, "CLASSIFIER_ARTIFACT_INVALID_LABELS"),
    ],
)
def test_joblib_lr_predictor_rejects_invalid_payloads(tmp_path, payload, expected_code):
    artifact_path = dump_payload(tmp_path, payload)

    with pytest.raises(JoblibLrClassifierLoadError) as exc_info:
        load_joblib_lr_predictor(artifact_path)

    assert exc_info.value.code == expected_code


def test_joblib_lr_predictor_rejects_invalid_payload_without_sensitive_metadata(tmp_path):
    payload = {
        "raw_prompt": "SENSITIVE_PROMPT_SENTINEL",
        "file_content": "SENSITIVE_FILE_CONTENT_SENTINEL",
        "extracted_text": "SENSITIVE_EXTRACTED_TEXT_SENTINEL",
        "detected_raw_value": "SENSITIVE_DETECTED_VALUE_SENTINEL",
        "original_filename": "SENSITIVE_FILENAME_SENTINEL",
    }
    artifact_path = dump_payload(tmp_path, payload)

    with pytest.raises(JoblibLrClassifierLoadError) as exc_info:
        load_joblib_lr_predictor(artifact_path)

    rendered = str(exc_info.value)
    assert exc_info.value.metadata == {}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILE_CONTENT_SENTINEL" not in rendered
    assert "SENSITIVE_EXTRACTED_TEXT_SENTINEL" not in rendered
    assert "SENSITIVE_DETECTED_VALUE_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_joblib_lr_predictor_converts_probability_rows_to_plain_floats(tmp_path):
    artifact_path = dump_payload(
        tmp_path,
        {
            "classifier": FakeProbabilityClassifier(((0, 1), (1, 0))),
            "target_labels": ("SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"),
        },
    )

    predictor = load_joblib_lr_predictor(artifact_path)

    assert predictor.predict_probabilities([[1.0], [2.0]]) == [[0.0, 1.0], [1.0, 0.0]]
