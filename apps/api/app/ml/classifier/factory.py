from collections.abc import Callable
from pathlib import Path

from app.ml.classifier.loader import JoblibLrClassifierLoadError, load_joblib_lr_predictor
from app.ml.classifier.models import ProbabilityPredictor
from app.ml.classifier.runtime import LrClassifierRuntime


class ClassifierRuntimeBuildError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


def build_lr_classifier_runtime(
    artifact_path: str | Path,
    *,
    loader: Callable[[str | Path], ProbabilityPredictor] = load_joblib_lr_predictor,
) -> LrClassifierRuntime:
    try:
        predictor = loader(artifact_path)
    except JoblibLrClassifierLoadError as exc:
        raise ClassifierRuntimeBuildError(
            code="CLASSIFIER_RUNTIME_BUILD_FAILED",
            message="classifier runtime could not be built",
            metadata={"loader_code": exc.code},
        ) from exc

    return LrClassifierRuntime(predictor)
