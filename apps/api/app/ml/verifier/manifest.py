import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any

from app.ml.verifier.models import VerifierArtifactRef
from app.ml.verifier.runtime import LabelDefinition


class VerifierManifestLoadError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


@dataclass(frozen=True)
class LoadedVerifierManifest:
    artifact: VerifierArtifactRef
    verifier_dir_path: Path
    artifact_root: Path
    target_labels: list[str]
    label_definitions: dict[str, LabelDefinition]
    thresholds: dict[str, float]
    max_length_tokens: int
    chunk_chars: int
    chunk_overlap: int
    max_chunks: int


def load_verifier_manifest(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
) -> LoadedVerifierManifest:
    path = Path(manifest_path)
    if not path.is_file():
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_NOT_FOUND", message="verifier manifest file was not found")

    payload = _read_json_file(
        path,
        invalid_code="VERIFIER_MANIFEST_INVALID_JSON",
        invalid_message="verifier manifest json is invalid",
    )
    if not isinstance(payload, dict):
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_INVALID_PAYLOAD", message="verifier manifest payload is invalid")

    manifest_version = _require_text(payload.get("manifest_version"), "manifest_version")
    selected = payload.get("selected")
    if not isinstance(selected, dict):
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_INVALID_SELECTED", message="verifier manifest selected payload is invalid")

    verifier_dir_path = _require_relative_path(selected.get("verifier_dir"), "selected.verifier_dir")
    label_definitions_path = _require_relative_path(selected.get("label_definitions_json"), "selected.label_definitions_json")
    target_labels_path = _require_relative_path(selected.get("target_labels_json"), "selected.target_labels_json")
    verifier_threshold_mode = _require_text(selected.get("verifier_threshold_mode"), "selected.verifier_threshold_mode")
    verifier_threshold = _require_threshold(selected.get("verifier_threshold"), "selected.verifier_threshold")
    max_length_tokens = _require_positive_int(selected.get("max_length_tokens"), "selected.max_length_tokens")
    chunk_chars = _require_positive_int(selected.get("chunk_chars"), "selected.chunk_chars")
    chunk_overlap = _require_nonnegative_int(selected.get("chunk_overlap"), "selected.chunk_overlap")
    max_chunks = _require_positive_int(selected.get("max_chunks"), "selected.max_chunks")

    if verifier_threshold_mode != "global":
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": "selected.verifier_threshold_mode"},
        )
    if chunk_overlap >= chunk_chars:
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": "selected.chunk_overlap"},
        )

    root = Path(artifact_root) if artifact_root is not None else _infer_artifact_root(path)
    target_labels = _coerce_target_labels(
        _read_json_file(
            root / target_labels_path,
            invalid_code="VERIFIER_MANIFEST_INVALID_LABELS_JSON",
            invalid_message="verifier manifest label json is invalid",
            not_found_code="VERIFIER_MANIFEST_LABELS_NOT_FOUND",
            not_found_message="verifier manifest label file was not found",
        )
    )
    label_definitions = _coerce_label_definitions(
        _read_json_file(
            root / label_definitions_path,
            invalid_code="VERIFIER_MANIFEST_INVALID_LABEL_DEFINITIONS_JSON",
            invalid_message="verifier manifest label definitions json is invalid",
            not_found_code="VERIFIER_MANIFEST_LABEL_DEFINITIONS_NOT_FOUND",
            not_found_message="verifier manifest label definitions file was not found",
        ),
        target_labels,
    )

    try:
        artifact = VerifierArtifactRef(
            artifact_id=manifest_version,
            model_version=verifier_dir_path.name,
            runtime_version=manifest_version,
        )
    except Exception as exc:
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_INVALID_PAYLOAD", message="verifier manifest payload is invalid") from exc

    return LoadedVerifierManifest(
        artifact=artifact,
        verifier_dir_path=verifier_dir_path,
        artifact_root=root,
        target_labels=target_labels,
        label_definitions=label_definitions,
        thresholds={label: verifier_threshold for label in target_labels},
        max_length_tokens=max_length_tokens,
        chunk_chars=chunk_chars,
        chunk_overlap=chunk_overlap,
        max_chunks=max_chunks,
    )


def _infer_artifact_root(manifest_path: Path) -> Path:
    if manifest_path.parent.name == "models":
        return manifest_path.parent.parent
    return manifest_path.parent


def _read_json_file(
    path: Path,
    *,
    invalid_code: str,
    invalid_message: str,
    not_found_code: str = "VERIFIER_MANIFEST_NOT_FOUND",
    not_found_message: str = "verifier manifest file was not found",
) -> Any:
    if not path.is_file():
        raise VerifierManifestLoadError(code=not_found_code, message=not_found_message)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        raise VerifierManifestLoadError(code=invalid_code, message=invalid_message) from exc


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": field},
        )
    return value


def _require_threshold(value: Any, field: str) -> float:
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": field},
        )
    threshold = float(value)
    if threshold < 0.0 or threshold > 1.0:
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": field},
        )
    return threshold


def _require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": field},
        )
    return value


def _require_nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_PAYLOAD",
            message="verifier manifest payload is invalid",
            metadata={"field": field},
        )
    return value


def _require_relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_MISSING_PATH",
            message="verifier manifest required path is missing",
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
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_UNSAFE_PATH",
            message="verifier manifest path is unsafe",
            metadata={"field": field},
        )
    return Path(*posix_path.parts)


def _coerce_target_labels(payload: Any) -> list[str]:
    value = payload.get("target_labels") if isinstance(payload, dict) else payload
    if not isinstance(value, list):
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_INVALID_LABELS", message="verifier manifest labels are invalid")
    labels = [label for label in value if isinstance(label, str) and label.strip()]
    if len(labels) != len(value) or not labels or len(set(labels)) != len(labels):
        raise VerifierManifestLoadError(code="VERIFIER_MANIFEST_INVALID_LABELS", message="verifier manifest labels are invalid")
    return labels


def _coerce_label_definitions(payload: Any, target_labels: list[str]) -> dict[str, LabelDefinition]:
    if not isinstance(payload, dict):
        raise VerifierManifestLoadError(
            code="VERIFIER_MANIFEST_INVALID_LABEL_DEFINITIONS",
            message="verifier manifest label definitions are invalid",
        )

    definitions: dict[str, LabelDefinition] = {}
    for label in target_labels:
        value = payload.get(label)
        if not isinstance(value, dict):
            raise VerifierManifestLoadError(
                code="VERIFIER_MANIFEST_INVALID_LABEL_DEFINITIONS",
                message="verifier manifest label definitions are invalid",
            )
        positive = value.get("positive")
        negative = value.get("negative")
        boundary = value.get("boundary")
        if not all(isinstance(item, str) and item.strip() for item in [positive, negative, boundary]):
            raise VerifierManifestLoadError(
                code="VERIFIER_MANIFEST_INVALID_LABEL_DEFINITIONS",
                message="verifier manifest label definitions are invalid",
            )
        definitions[label] = LabelDefinition(positive=positive, negative=negative, boundary=boundary)
    return definitions
