import json
from pathlib import Path

import pytest

from app.ml.verifier.manifest import VerifierManifestLoadError, load_verifier_manifest


DEFAULT_SELECTED = object()


def write_manifest_bundle(
    tmp_path: Path,
    *,
    selected: object = DEFAULT_SELECTED,
    labels_payload: object | None = None,
    definitions_payload: object | None = None,
) -> Path:
    models_dir = tmp_path / "models"
    verifier_dir = models_dir / "context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6"
    verifier_dir.mkdir(parents=True)
    manifest_path = models_dir / "context_lr_roberta_best_v205_manifest.json"

    (tmp_path / "context_target_labels.json").write_text(
        json.dumps(labels_payload if labels_payload is not None else {"target_labels": ["SECRET_CREDENTIAL_CONTEXT"]}),
        encoding="utf-8",
    )
    (tmp_path / "context_label_definitions.json").write_text(
        json.dumps(
            definitions_payload
            if definitions_payload is not None
            else {
                "SECRET_CREDENTIAL_CONTEXT": {
                    "positive": "YES when an actual credential appears.",
                    "negative": "NO for placeholder-only examples.",
                    "boundary": "Filled value is decisive.",
                }
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "context_lr_roberta_best_v205",
                "selected": {
                    "verifier_dir": "models/context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6",
                    "label_definitions_json": "context_label_definitions.json",
                    "target_labels_json": "context_target_labels.json",
                    "verifier_threshold_mode": "global",
                    "verifier_threshold": 0.475,
                    "max_length_tokens": 384,
                    "chunk_chars": 900,
                    "chunk_overlap": 120,
                    "max_chunks": 8,
                }
                if selected is DEFAULT_SELECTED
                else selected,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_verifier_manifest_loader_reads_selected_roberta_artifact_ref(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)

    loaded = load_verifier_manifest(manifest_path)

    assert loaded.verifier_dir_path == Path("models/context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6")
    assert loaded.artifact.artifact_id == "context_lr_roberta_best_v205"
    assert loaded.artifact.model_version == "context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6"
    assert loaded.artifact.runtime_version == "context_lr_roberta_best_v205"
    assert loaded.target_labels == ["SECRET_CREDENTIAL_CONTEXT"]
    assert loaded.thresholds == {"SECRET_CREDENTIAL_CONTEXT": 0.475}
    assert loaded.max_length_tokens == 384
    assert loaded.chunk_chars == 900
    assert loaded.chunk_overlap == 120
    assert loaded.max_chunks == 8
    assert loaded.label_definitions["SECRET_CREDENTIAL_CONTEXT"].positive == "YES when an actual credential appears."


def test_verifier_manifest_loader_reads_v287_labelwise_thresholds_and_chunk_policy(tmp_path):
    models_dir = tmp_path / "models"
    verifier_dir = models_dir / "context_verifier_klue_roberta_base_lrmined_v287_global002_compactv2_lpft_focal_1p2ep"
    verifier_dir.mkdir(parents=True)
    labels = ["SECRET_CREDENTIAL_CONTEXT", "PERSONAL_DATA_CONTEXT"]
    (tmp_path / "context_target_labels.json").write_text(json.dumps({"target_labels": labels}), encoding="utf-8")
    (tmp_path / "context_label_definitions_verifier_compact_v2.json").write_text(
        json.dumps(
            {
                "SECRET_CREDENTIAL_CONTEXT": {
                    "positive": "YES when an actual credential appears.",
                    "negative": "NO for placeholder-only examples.",
                    "boundary": "Filled value is decisive.",
                },
                "PERSONAL_DATA_CONTEXT": {
                    "positive": "YES when personal data appears.",
                    "negative": "NO for synthetic labels only.",
                    "boundary": "Real person data is decisive.",
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path = models_dir / "context_lr_roberta_active_best_f1_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "context_lr_roberta_active_best_f1_2026_06_23",
                "selected": {
                    "verifier_dir": "models/context_verifier_klue_roberta_base_lrmined_v287_global002_compactv2_lpft_focal_1p2ep",
                    "target_labels_json": "context_target_labels.json",
                    "label_definitions_json": "context_label_definitions_verifier_compact_v2.json",
                    "verifier_threshold_mode": "labelwise",
                    "verifier_thresholds": {
                        "SECRET_CREDENTIAL_CONTEXT": 0.915,
                        "PERSONAL_DATA_CONTEXT": 0.48,
                    },
                    "max_length_tokens": 384,
                    "chunk_policy": {
                        "chunk_chars": 900,
                        "chunk_overlap": 120,
                        "max_chunks": 8,
                        "pooling": "max verifier score per label across chunks",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_verifier_manifest(manifest_path)

    assert loaded.thresholds == {"SECRET_CREDENTIAL_CONTEXT": 0.915, "PERSONAL_DATA_CONTEXT": 0.48}
    assert loaded.chunk_chars == 900
    assert loaded.chunk_overlap == 120
    assert loaded.max_chunks == 8
    assert loaded.verifier_dir_path == Path(
        "models/context_verifier_klue_roberta_base_lrmined_v287_global002_compactv2_lpft_focal_1p2ep"
    )


@pytest.mark.parametrize(
    ("field", "path_value"),
    [
        ("verifier_dir", "../escape"),
        ("verifier_dir", "/tmp/SENSITIVE_FILENAME_SENTINEL"),
        ("verifier_dir", "C:/Users/example/SENSITIVE_FILENAME_SENTINEL"),
        ("label_definitions_json", "../context_label_definitions.json"),
        ("label_definitions_json", "/tmp/SENSITIVE_FILENAME_SENTINEL.json"),
        ("target_labels_json", "../context_target_labels.json"),
    ],
)
def test_verifier_manifest_loader_rejects_unsafe_paths_without_sensitive_metadata(tmp_path, field, path_value):
    selected = {
        "verifier_dir": "models/context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6",
        "label_definitions_json": "context_label_definitions.json",
        "target_labels_json": "context_target_labels.json",
        "verifier_threshold_mode": "global",
        "verifier_threshold": 0.475,
        "max_length_tokens": 384,
        "chunk_chars": 900,
        "chunk_overlap": 120,
        "max_chunks": 8,
    }
    selected[field] = path_value
    manifest_path = write_manifest_bundle(tmp_path, selected=selected)

    with pytest.raises(VerifierManifestLoadError) as exc_info:
        load_verifier_manifest(manifest_path)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "VERIFIER_MANIFEST_UNSAFE_PATH"
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
    assert "C:/Users/example" not in rendered
    assert "/tmp/" not in rendered


@pytest.mark.parametrize(
    ("selected", "expected_code"),
    [
        (None, "VERIFIER_MANIFEST_INVALID_SELECTED"),
        ({"target_labels_json": "context_target_labels.json"}, "VERIFIER_MANIFEST_MISSING_PATH"),
        (
            {
                "verifier_dir": "models/verifier",
                "label_definitions_json": "context_label_definitions.json",
                "target_labels_json": "context_target_labels.json",
                "verifier_threshold_mode": "global",
                "verifier_threshold": 1.001,
            },
            "VERIFIER_MANIFEST_INVALID_PAYLOAD",
        ),
        (
            {
                "verifier_dir": "models/verifier",
                "label_definitions_json": "context_label_definitions.json",
                "target_labels_json": "context_target_labels.json",
                "verifier_threshold_mode": "labelwise",
                "verifier_thresholds": {"SECRET_CREDENTIAL_CONTEXT": 0.5, "EXTRA_CONTEXT": 0.5},
                "max_length_tokens": 384,
                "chunk_policy": {
                    "chunk_chars": 900,
                    "chunk_overlap": 120,
                    "max_chunks": 8,
                    "pooling": "max verifier score per label across chunks",
                },
            },
            "VERIFIER_MANIFEST_INVALID_PAYLOAD",
        ),
    ],
)
def test_verifier_manifest_loader_rejects_invalid_selected_payloads(tmp_path, selected, expected_code):
    manifest_path = write_manifest_bundle(tmp_path, selected=selected)

    with pytest.raises(VerifierManifestLoadError) as exc_info:
        load_verifier_manifest(manifest_path)

    assert exc_info.value.code == expected_code


def test_verifier_manifest_loader_rejects_malformed_json_without_sensitive_metadata(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)
    manifest_path.write_text(
        '{"raw_prompt": "SENSITIVE_PROMPT_SENTINEL", "original_filename": "SENSITIVE_FILENAME_SENTINEL"',
        encoding="utf-8",
    )

    with pytest.raises(VerifierManifestLoadError) as exc_info:
        load_verifier_manifest(manifest_path)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "VERIFIER_MANIFEST_INVALID_JSON"
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
