from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.atoms.models import PipelineFailure
from app.core.config import Settings
from app.ml.classifier.loader import JoblibLrClassifierLoadError, load_joblib_lr_predictor
from app.ml.classifier.manifest import ClassifierManifestLoadError, LoadedClassifierManifest, load_classifier_manifest
from app.ml.classifier.models import ClassifierArtifactRef, ProbabilityPredictor
from app.ml.classifier.runtime import LrClassifierRuntime
from app.ml.classifier.service import ClassifierService


class ClassifierRuntimeBuildError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class ClassifierServiceBuildError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


@dataclass(frozen=True)
class BuiltClassifierService:
    service: ClassifierService
    artifact: ClassifierArtifactRef


@dataclass(frozen=True)
class ClassifierRuntimeProviderResult:
    bundle: BuiltClassifierService | None = None
    failure: PipelineFailure | None = None

    @property
    def available(self) -> bool:
        return self.bundle is not None and self.failure is None


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


def build_classifier_service_from_manifest(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
    manifest_loader: Callable[..., LoadedClassifierManifest] = load_classifier_manifest,
    runtime_builder: Callable[[Path], LrClassifierRuntime] = build_lr_classifier_runtime,
) -> BuiltClassifierService:
    try:
        loaded_manifest = manifest_loader(manifest_path, artifact_root=artifact_root)
    except ClassifierManifestLoadError as exc:
        raise ClassifierServiceBuildError(
            code="CLASSIFIER_SERVICE_BUILD_FAILED",
            message="classifier service could not be built",
            metadata={"manifest_code": exc.code},
        ) from exc
    except Exception as exc:
        raise ClassifierServiceBuildError(
            code="CLASSIFIER_SERVICE_BUILD_FAILED",
            message="classifier service could not be built",
            metadata={"manifest_code": "CLASSIFIER_MANIFEST_LOAD_FAILED"},
        ) from exc

    try:
        runtime = runtime_builder(loaded_manifest.artifact_root / loaded_manifest.lr_model_path)
    except ClassifierRuntimeBuildError as exc:
        raise ClassifierServiceBuildError(
            code="CLASSIFIER_SERVICE_BUILD_FAILED",
            message="classifier service could not be built",
            metadata={"runtime_code": exc.code},
        ) from exc
    except Exception as exc:
        raise ClassifierServiceBuildError(
            code="CLASSIFIER_SERVICE_BUILD_FAILED",
            message="classifier service could not be built",
            metadata={"runtime_code": "CLASSIFIER_RUNTIME_BUILD_FAILED"},
        ) from exc

    return BuiltClassifierService(service=ClassifierService(runtime), artifact=loaded_manifest.artifact)


def build_classifier_service_from_settings(
    settings: Settings,
    *,
    builder: Callable[[Path], BuiltClassifierService] = build_classifier_service_from_manifest,
) -> ClassifierRuntimeProviderResult:
    if not settings.classifier_runtime_enabled:
        return ClassifierRuntimeProviderResult(
            failure=PipelineFailure(
                code="CLASSIFIER_RUNTIME_DISABLED",
                message="classifier runtime disabled",
                metadata={"status": "disabled"},
            ),
        )

    manifest_path = settings.classifier_manifest_path_value()
    if manifest_path is None:
        return ClassifierRuntimeProviderResult(
            failure=PipelineFailure(
                code="CLASSIFIER_MANIFEST_NOT_CONFIGURED",
                message="classifier manifest path is not configured",
                metadata={"status": "unavailable"},
            ),
        )

    try:
        bundle = builder(manifest_path)
    except ClassifierServiceBuildError as exc:
        return ClassifierRuntimeProviderResult(
            failure=PipelineFailure(
                code="CLASSIFIER_RUNTIME_UNAVAILABLE",
                message="classifier runtime unavailable",
                metadata={
                    "status": "unavailable",
                    "build_code": exc.code,
                },
            ),
        )
    except Exception:
        return ClassifierRuntimeProviderResult(
            failure=PipelineFailure(
                code="CLASSIFIER_RUNTIME_UNAVAILABLE",
                message="classifier runtime unavailable",
                metadata={
                    "status": "unavailable",
                    "build_code": "CLASSIFIER_SERVICE_BUILD_FAILED",
                },
            ),
        )

    return ClassifierRuntimeProviderResult(bundle=bundle)
