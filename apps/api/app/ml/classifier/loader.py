from pathlib import Path
from typing import Any


class JoblibLrClassifierLoadError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class JoblibLrProbabilityPredictor:
    def __init__(self, classifier: Any, target_labels: list[str], embedding_model_version: str | None = None) -> None:
        self._classifier = classifier
        self.target_labels = target_labels
        self.embedding_model_version = embedding_model_version

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        probability_rows = self._classifier.predict_proba(vectors)
        return [[float(score) for score in row] for row in probability_rows]


def load_joblib_lr_predictor(artifact_path: str | Path) -> JoblibLrProbabilityPredictor:
    try:
        import joblib
    except ImportError as exc:
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_DEPENDENCY_MISSING",
            message="classifier artifact dependency is unavailable",
        ) from exc

    path = Path(artifact_path)
    if not path.is_file():
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_NOT_FOUND",
            message="classifier artifact file was not found",
        )

    # joblib uses pickle semantics; callers must only pass trusted build artifacts.
    try:
        payload = joblib.load(path)
    except Exception as exc:
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_LOAD_FAILED",
            message="classifier artifact could not be loaded",
        ) from exc

    if not isinstance(payload, dict):
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_INVALID_PAYLOAD",
            message="classifier artifact payload is invalid",
        )

    classifier = payload.get("classifier")
    if classifier is None:
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_MISSING_CLASSIFIER",
            message="classifier artifact classifier is missing",
        )
    if not callable(getattr(classifier, "predict_proba", None)):
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_INVALID_CLASSIFIER",
            message="classifier artifact classifier is invalid",
        )

    target_labels = _coerce_target_labels(payload.get("target_labels"))
    embedding_model = payload.get("embedding_model")
    embedding_model_version = embedding_model if isinstance(embedding_model, str) and embedding_model.strip() else None

    return JoblibLrProbabilityPredictor(
        classifier=classifier,
        target_labels=target_labels,
        embedding_model_version=embedding_model_version,
    )


def _coerce_target_labels(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_INVALID_LABELS",
            message="classifier artifact labels are invalid",
        )

    labels = [label for label in value if isinstance(label, str) and label.strip()]
    if len(labels) != len(value) or not labels or len(set(labels)) != len(labels):
        raise JoblibLrClassifierLoadError(
            code="CLASSIFIER_ARTIFACT_INVALID_LABELS",
            message="classifier artifact labels are invalid",
        )
    return labels
