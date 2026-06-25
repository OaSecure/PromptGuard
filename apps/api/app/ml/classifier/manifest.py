import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any

from app.ml.classifier.models import ClassifierArtifactRef


EMBEDDING_MODEL_VERSION = "Qwen/Qwen3-Embedding-0.6B"


class ClassifierManifestLoadError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


@dataclass(frozen=True)
class LoadedClassifierManifest:
    artifact: ClassifierArtifactRef
    lr_model_path: Path
    artifact_root: Path


def build_classifier_artifact_ref(
    *,
    artifact_id: str,
    manifest_version: str,
    runtime_version: str,
    target_labels: list[str],
    candidate_threshold: float,
    embedding_model_version: str,
) -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id=artifact_id,
        manifest_version=manifest_version,
        runtime_version=runtime_version,
        target_labels=target_labels,
        candidate_threshold=candidate_threshold,
        embedding_model_version=embedding_model_version,
    )


def load_classifier_manifest(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
) -> LoadedClassifierManifest:
    path = Path(manifest_path)
    if not path.is_file():
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_NOT_FOUND",
            message="classifier manifest file was not found",
        )

    payload = _read_json_file(
        path,
        invalid_code="CLASSIFIER_MANIFEST_INVALID_JSON",
        invalid_message="classifier manifest json is invalid",
    )
    if not isinstance(payload, dict):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
        )

    manifest_version = _require_text(payload.get("manifest_version"), "manifest_version")
    selected = payload.get("selected")
    if not isinstance(selected, dict):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_SELECTED",
            message="classifier manifest selected payload is invalid",
        )

    lr_model_path = _require_relative_path(selected.get("lr_model"), "selected.lr_model")
    target_labels_path = _require_relative_path(selected.get("target_labels_json"), "selected.target_labels_json")
    candidate_threshold = _read_candidate_threshold(selected)

    root = Path(artifact_root) if artifact_root is not None else _infer_artifact_root(path)
    labels_payload = _read_json_file(
        _resolve_json_path(root, target_labels_path, manifest_dir=path.parent),
        invalid_code="CLASSIFIER_MANIFEST_INVALID_LABELS_JSON",
        invalid_message="classifier manifest label json is invalid",
        not_found_code="CLASSIFIER_MANIFEST_LABELS_NOT_FOUND",
        not_found_message="classifier manifest label file was not found",
    )
    target_labels = _coerce_target_labels(labels_payload)

    try:
        artifact = build_classifier_artifact_ref(
            artifact_id=manifest_version,
            manifest_version=manifest_version,
            runtime_version=manifest_version,
            target_labels=target_labels,
            candidate_threshold=candidate_threshold,
            embedding_model_version=EMBEDDING_MODEL_VERSION,
        )
    except Exception as exc:
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
        ) from exc

    return LoadedClassifierManifest(artifact=artifact, lr_model_path=lr_model_path, artifact_root=root)


def _infer_artifact_root(manifest_path: Path) -> Path:
    if manifest_path.parent.name == "models":
        return manifest_path.parent.parent
    return manifest_path.parent


def _resolve_json_path(root: Path, relative_path: Path, *, manifest_dir: Path) -> Path:
    root_candidate = root / relative_path
    if root_candidate.is_file():
        return root_candidate

    manifest_dir_candidate = manifest_dir / relative_path
    if manifest_dir_candidate.is_file():
        return manifest_dir_candidate

    return root_candidate


def _read_json_file(
    path: Path,
    *,
    invalid_code: str,
    invalid_message: str,
    not_found_code: str = "CLASSIFIER_MANIFEST_NOT_FOUND",
    not_found_message: str = "classifier manifest file was not found",
) -> Any:
    if not path.is_file():
        raise ClassifierManifestLoadError(code=not_found_code, message=not_found_message)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        raise ClassifierManifestLoadError(code=invalid_code, message=invalid_message) from exc


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
            metadata={"field": field},
        )
    return value


def _read_candidate_threshold(selected: dict[str, Any]) -> float:
    if "candidate_threshold" in selected:
        return _require_threshold(selected.get("candidate_threshold"), "selected.candidate_threshold")

    policy = selected.get("lr_candidate_policy")
    if not isinstance(policy, dict):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
            metadata={"field": "selected.lr_candidate_policy"},
        )

    mode = policy.get("mode")
    if mode != "global_high_recall_threshold":
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
            metadata={"field": "selected.lr_candidate_policy.mode"},
        )
    return _require_threshold(
        policy.get("candidate_threshold"),
        "selected.lr_candidate_policy.candidate_threshold",
    )


def _require_threshold(value: Any, field: str) -> float:
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
            metadata={"field": field},
        )
    threshold = float(value)
    if threshold < 0.0 or threshold > 1.0:
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
            message="classifier manifest payload is invalid",
            metadata={"field": field},
        )
    return threshold


def _require_relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_MISSING_PATH",
            message="classifier manifest required path is missing",
            metadata={"field": field},
        )

    normalized = value.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    first_part = posix_path.parts[0] if posix_path.parts else ""
    if (
        Path(value).is_absolute()
        or posix_path.is_absolute()
        or ".." in posix_path.parts
        or not posix_path.parts
        or ":" in first_part
    ):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_UNSAFE_PATH",
            message="classifier manifest path is unsafe",
            metadata={"field": field},
        )
    return Path(*posix_path.parts)


def _coerce_target_labels(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        value = payload.get("target_labels")
    else:
        value = payload

    if not isinstance(value, list):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_LABELS",
            message="classifier manifest labels are invalid",
        )

    labels = [label for label in value if isinstance(label, str) and label.strip()]
    if len(labels) != len(value) or not labels or len(set(labels)) != len(labels):
        raise ClassifierManifestLoadError(
            code="CLASSIFIER_MANIFEST_INVALID_LABELS",
            message="classifier manifest labels are invalid",
        )
    return labels
