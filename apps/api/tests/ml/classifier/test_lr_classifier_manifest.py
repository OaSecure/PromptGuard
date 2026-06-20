import json
from pathlib import Path

import pytest

from app.ml.classifier.manifest import ClassifierManifestLoadError, load_classifier_manifest


DEFAULT_SELECTED = object()


def write_manifest_bundle(
    tmp_path,
    *,
    selected: object = DEFAULT_SELECTED,
    labels_payload: object | None = None,
) -> Path:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    manifest_path = models_dir / "context_lr_roberta_best_v205_manifest.json"
    target_labels_path = tmp_path / "context_target_labels.json"

    target_labels_path.write_text(
        json.dumps(
            labels_payload
            if labels_payload is not None
            else {
                "target_labels": [
                    "SECRET_CREDENTIAL_CONTEXT",
                    "PERSONAL_DATA_CONTEXT",
                    "BULK_SENSITIVE_RECORD_CONTEXT",
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "context_lr_roberta_best_v205",
                "selected": {
                    "lr_model": "models/context_with_patch_v205_deploy_candidate_classifier.joblib",
                    "target_labels_json": "context_target_labels.json",
                    "candidate_threshold": 0.575,
                }
                if selected is DEFAULT_SELECTED
                else selected,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_classifier_manifest_loader_reads_selected_lr_artifact_ref(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)

    loaded = load_classifier_manifest(manifest_path)

    assert loaded.lr_model_path == Path("models/context_with_patch_v205_deploy_candidate_classifier.joblib")
    assert loaded.artifact.artifact_id == "context_lr_roberta_best_v205"
    assert loaded.artifact.manifest_version == "context_lr_roberta_best_v205"
    assert loaded.artifact.runtime_version == "context_lr_roberta_best_v205"
    assert loaded.artifact.target_labels == [
        "SECRET_CREDENTIAL_CONTEXT",
        "PERSONAL_DATA_CONTEXT",
        "BULK_SENSITIVE_RECORD_CONTEXT",
    ]
    assert loaded.artifact.candidate_threshold == 0.575
    assert loaded.artifact.embedding_model_version == "Qwen/Qwen3-Embedding-0.6B"


def test_classifier_manifest_loader_accepts_target_label_list_payload(tmp_path):
    manifest_path = write_manifest_bundle(
        tmp_path,
        labels_payload=["SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"],
    )

    loaded = load_classifier_manifest(manifest_path)

    assert loaded.artifact.target_labels == ["SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"]


@pytest.mark.parametrize(
    ("field", "path_value"),
    [
        ("lr_model", "../escape.joblib"),
        ("lr_model", "/tmp/SENSITIVE_FILENAME_SENTINEL.joblib"),
        ("lr_model", "C:/Users/example/SENSITIVE_FILENAME_SENTINEL.joblib"),
        ("target_labels_json", "../context_target_labels.json"),
        ("target_labels_json", "/tmp/SENSITIVE_FILENAME_SENTINEL.json"),
        ("target_labels_json", "C:/Users/example/SENSITIVE_FILENAME_SENTINEL.json"),
    ],
)
def test_classifier_manifest_loader_rejects_unsafe_relative_paths_without_sensitive_metadata(tmp_path, field, path_value):
    selected = {
        "lr_model": "models/context_with_patch_v205_deploy_candidate_classifier.joblib",
        "target_labels_json": "context_target_labels.json",
        "candidate_threshold": 0.575,
    }
    selected[field] = path_value
    manifest_path = write_manifest_bundle(tmp_path, selected=selected)

    with pytest.raises(ClassifierManifestLoadError) as exc_info:
        load_classifier_manifest(manifest_path)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_MANIFEST_UNSAFE_PATH"
    assert exc_info.value.metadata == {"field": f"selected.{field}"}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
    assert "C:/Users/example" not in rendered
    assert "/tmp/" not in rendered


@pytest.mark.parametrize(
    ("selected", "expected_code"),
    [
        (None, "CLASSIFIER_MANIFEST_INVALID_SELECTED"),
        ({"target_labels_json": "context_target_labels.json", "candidate_threshold": 0.575}, "CLASSIFIER_MANIFEST_MISSING_PATH"),
        ({"lr_model": "models/classifier.joblib", "candidate_threshold": 0.575}, "CLASSIFIER_MANIFEST_MISSING_PATH"),
        (
            {
                "lr_model": "models/classifier.joblib",
                "target_labels_json": "context_target_labels.json",
                "candidate_threshold": 1.001,
            },
            "CLASSIFIER_MANIFEST_INVALID_PAYLOAD",
        ),
    ],
)
def test_classifier_manifest_loader_rejects_invalid_selected_payloads(tmp_path, selected, expected_code):
    manifest_path = write_manifest_bundle(tmp_path, selected=selected)

    with pytest.raises(ClassifierManifestLoadError) as exc_info:
        load_classifier_manifest(manifest_path)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "labels_payload",
    [
        {"target_labels": []},
        {"target_labels": ["SECRET_CREDENTIAL_CONTEXT", "SECRET_CREDENTIAL_CONTEXT"]},
        {"target_labels": ["SECRET_CREDENTIAL_CONTEXT", ""]},
        {"labels": ["SECRET_CREDENTIAL_CONTEXT"]},
        "SECRET_CREDENTIAL_CONTEXT",
    ],
)
def test_classifier_manifest_loader_rejects_invalid_target_label_payloads(tmp_path, labels_payload):
    manifest_path = write_manifest_bundle(tmp_path, labels_payload=labels_payload)

    with pytest.raises(ClassifierManifestLoadError) as exc_info:
        load_classifier_manifest(manifest_path)

    assert exc_info.value.code == "CLASSIFIER_MANIFEST_INVALID_LABELS"


def test_classifier_manifest_loader_rejects_missing_label_file_without_sensitive_metadata(tmp_path):
    manifest_path = write_manifest_bundle(
        tmp_path,
        selected={
            "lr_model": "models/context_with_patch_v205_deploy_candidate_classifier.joblib",
            "target_labels_json": "SENSITIVE_FILENAME_SENTINEL.json",
            "candidate_threshold": 0.575,
        },
    )

    with pytest.raises(ClassifierManifestLoadError) as exc_info:
        load_classifier_manifest(manifest_path)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_MANIFEST_LABELS_NOT_FOUND"
    assert exc_info.value.metadata == {}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_classifier_manifest_loader_rejects_malformed_json_without_sensitive_metadata(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)
    manifest_path.write_text(
        '{"raw_prompt": "SENSITIVE_PROMPT_SENTINEL", "original_filename": "SENSITIVE_FILENAME_SENTINEL"',
        encoding="utf-8",
    )

    with pytest.raises(ClassifierManifestLoadError) as exc_info:
        load_classifier_manifest(manifest_path)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_MANIFEST_INVALID_JSON"
    assert exc_info.value.metadata == {}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
