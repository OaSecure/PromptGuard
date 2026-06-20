from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.ml.verifier.loader import RobertaVerifierLoadError, load_huggingface_roberta_pair_scorer
from app.ml.verifier.manifest import LoadedVerifierManifest, VerifierManifestLoadError, load_verifier_manifest
from app.ml.verifier.models import VerifierArtifactRef
from app.ml.verifier.runtime import LabelDefinition, RobertaVerifierRuntime, VerifierPairScorer
from app.ml.verifier.service import RobertaVerifierService


class VerifierRuntimeBuildError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class VerifierServiceBuildError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


@dataclass(frozen=True)
class BuiltVerifierService:
    service: RobertaVerifierService
    artifact: VerifierArtifactRef


def build_roberta_verifier_runtime(
    verifier_dir: str | Path,
    *,
    label_definitions: Mapping[str, LabelDefinition | Mapping[str, str]],
    thresholds: Mapping[str, float],
    model_version: str,
    max_length_tokens: int = 384,
    chunk_chars: int = 900,
    chunk_overlap: int = 120,
    max_chunks: int = 8,
    loader: Callable[[str | Path], VerifierPairScorer] = load_huggingface_roberta_pair_scorer,
) -> RobertaVerifierRuntime:
    try:
        pair_scorer = loader(verifier_dir)
    except RobertaVerifierLoadError as exc:
        raise VerifierRuntimeBuildError(
            code="VERIFIER_RUNTIME_BUILD_FAILED",
            message="verifier runtime could not be built",
            metadata={"loader_code": exc.code},
        ) from exc

    return RobertaVerifierRuntime(
        pair_scorer=pair_scorer,
        label_definitions=_coerce_label_definitions(label_definitions),
        thresholds={label: float(threshold) for label, threshold in thresholds.items()},
        model_version=model_version,
        max_length_tokens=max_length_tokens,
        chunk_chars=chunk_chars,
        chunk_overlap=chunk_overlap,
        max_chunks=max_chunks,
    )


def build_verifier_service_from_manifest(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
    manifest_loader: Callable[..., LoadedVerifierManifest] = load_verifier_manifest,
    runtime_builder: Callable[..., RobertaVerifierRuntime] = build_roberta_verifier_runtime,
) -> BuiltVerifierService:
    try:
        loaded_manifest = manifest_loader(manifest_path, artifact_root=artifact_root)
    except VerifierManifestLoadError as exc:
        raise VerifierServiceBuildError(
            code="VERIFIER_SERVICE_BUILD_FAILED",
            message="verifier service could not be built",
            metadata={"manifest_code": exc.code},
        ) from exc
    except Exception as exc:
        raise VerifierServiceBuildError(
            code="VERIFIER_SERVICE_BUILD_FAILED",
            message="verifier service could not be built",
            metadata={"manifest_code": "VERIFIER_MANIFEST_LOAD_FAILED"},
        ) from exc

    try:
        runtime = runtime_builder(
            loaded_manifest.artifact_root / loaded_manifest.verifier_dir_path,
            label_definitions=loaded_manifest.label_definitions,
            thresholds=loaded_manifest.thresholds,
            model_version=loaded_manifest.artifact.model_version,
            max_length_tokens=loaded_manifest.max_length_tokens,
            chunk_chars=loaded_manifest.chunk_chars,
            chunk_overlap=loaded_manifest.chunk_overlap,
            max_chunks=loaded_manifest.max_chunks,
        )
    except VerifierRuntimeBuildError as exc:
        raise VerifierServiceBuildError(
            code="VERIFIER_SERVICE_BUILD_FAILED",
            message="verifier service could not be built",
            metadata={"runtime_code": exc.code},
        ) from exc
    except Exception as exc:
        raise VerifierServiceBuildError(
            code="VERIFIER_SERVICE_BUILD_FAILED",
            message="verifier service could not be built",
            metadata={"runtime_code": "VERIFIER_RUNTIME_BUILD_FAILED"},
        ) from exc

    return BuiltVerifierService(service=RobertaVerifierService(runtime), artifact=loaded_manifest.artifact)


def _coerce_label_definitions(label_definitions: Mapping[str, LabelDefinition | Mapping[str, str]]) -> dict[str, LabelDefinition]:
    coerced: dict[str, LabelDefinition] = {}
    for label, definition in label_definitions.items():
        if isinstance(definition, LabelDefinition):
            coerced[label] = definition
            continue
        coerced[label] = LabelDefinition(
            positive=str(definition["positive"]),
            negative=str(definition["negative"]),
            boundary=str(definition["boundary"]),
        )
    return coerced
