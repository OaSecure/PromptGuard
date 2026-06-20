import json
from pathlib import Path

import pytest

from app.ml.classifier import SegmentClassificationRequest
from app.ml.classifier.factory import (
    BuiltClassifierService,
    ClassifierRuntimeBuildError,
    ClassifierServiceBuildError,
    build_classifier_service_from_manifest,
)
from app.ml.classifier.manifest import ClassifierManifestLoadError
from app.ml.segment_embedding import SegmentEmbedding


def write_manifest_bundle(tmp_path: Path) -> Path:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    manifest_path = models_dir / "context_lr_roberta_best_v205_manifest.json"

    (tmp_path / "context_target_labels.json").write_text(
        json.dumps({"target_labels": ["secret", "credential"]}),
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
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


class FakeRuntime:
    def __init__(self) -> None:
        self.seen_request: SegmentClassificationRequest | None = None

    def classify(self, request: SegmentClassificationRequest):
        self.seen_request = request
        from app.ml.classifier import SegmentClassificationCandidate, SegmentClassificationResult

        return SegmentClassificationResult(
            input_id=request.input_id,
            candidates=[
                SegmentClassificationCandidate(
                    segment_id="segment-1",
                    label="secret",
                    score=0.99,
                    threshold=request.artifact.candidate_threshold,
                    artifact_id=request.artifact.artifact_id,
                    runtime_version=request.artifact.runtime_version,
                )
            ],
        )


def classification_request(bundle: BuiltClassifierService) -> SegmentClassificationRequest:
    return SegmentClassificationRequest(
        input_id="input-1",
        segment_embeddings=[
            SegmentEmbedding(
                segment_id="segment-1",
                vector=[0.1, 0.2],
                embedding_model_version=bundle.artifact.embedding_model_version,
                dimension=2,
                pooling="mean",
                normalized=True,
            )
        ],
        artifact=bundle.artifact,
    )


def test_manifest_backed_classifier_service_factory_builds_service_bundle(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)
    runtime = FakeRuntime()
    seen_paths: list[Path] = []

    def runtime_builder(path: Path):
        seen_paths.append(path)
        return runtime

    bundle = build_classifier_service_from_manifest(manifest_path, runtime_builder=runtime_builder)
    result = bundle.service.classify(classification_request(bundle))

    assert seen_paths == [tmp_path / "models" / "context_with_patch_v205_deploy_candidate_classifier.joblib"]
    assert bundle.artifact.artifact_id == "context_lr_roberta_best_v205"
    assert bundle.artifact.target_labels == ["secret", "credential"]
    assert bundle.artifact.candidate_threshold == 0.575
    assert result.failure is None
    assert [(candidate.label, candidate.artifact_id, candidate.runtime_version) for candidate in result.candidates] == [
        ("secret", "context_lr_roberta_best_v205", "context_lr_roberta_best_v205")
    ]


def test_manifest_backed_classifier_service_factory_resolves_artifact_root_override(tmp_path):
    artifact_root = tmp_path / "artifact-root"
    manifest_path = write_manifest_bundle(artifact_root)
    runtime = FakeRuntime()
    seen_paths: list[Path] = []

    def runtime_builder(path: Path):
        seen_paths.append(path)
        return runtime

    bundle = build_classifier_service_from_manifest(
        manifest_path,
        artifact_root=artifact_root,
        runtime_builder=runtime_builder,
    )

    assert seen_paths == [artifact_root / "models" / "context_with_patch_v205_deploy_candidate_classifier.joblib"]
    assert bundle.artifact.manifest_version == "context_lr_roberta_best_v205"


def test_manifest_backed_classifier_service_factory_wraps_manifest_failure_without_sensitive_values(tmp_path):
    missing_manifest = tmp_path / "SENSITIVE_FILENAME_SENTINEL_manifest.json"

    with pytest.raises(ClassifierServiceBuildError) as exc_info:
        build_classifier_service_from_manifest(missing_manifest)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"manifest_code": "CLASSIFIER_MANIFEST_NOT_FOUND"}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_manifest_backed_classifier_service_factory_wraps_runtime_failure_without_sensitive_values(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)

    def runtime_builder(path: Path):
        raise ClassifierRuntimeBuildError(
            code="CLASSIFIER_RUNTIME_BUILD_FAILED",
            message="classifier runtime could not be built",
            metadata={
                "raw_prompt": "SENSITIVE_PROMPT_SENTINEL",
                "original_filename": "SENSITIVE_FILENAME_SENTINEL",
            },
        )

    with pytest.raises(ClassifierServiceBuildError) as exc_info:
        build_classifier_service_from_manifest(manifest_path, runtime_builder=runtime_builder)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"runtime_code": "CLASSIFIER_RUNTIME_BUILD_FAILED"}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_manifest_backed_classifier_service_factory_wraps_unexpected_manifest_failure(tmp_path):
    def manifest_loader(path: Path, *, artifact_root: Path | None = None):
        raise RuntimeError("SENSITIVE_FILENAME_SENTINEL")

    with pytest.raises(ClassifierServiceBuildError) as exc_info:
        build_classifier_service_from_manifest(tmp_path / "manifest.json", manifest_loader=manifest_loader)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"manifest_code": "CLASSIFIER_MANIFEST_LOAD_FAILED"}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_manifest_backed_classifier_service_factory_wraps_unexpected_runtime_builder_failure(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)

    def runtime_builder(path: Path):
        raise RuntimeError("SENSITIVE_FILENAME_SENTINEL 0.12345")

    with pytest.raises(ClassifierServiceBuildError) as exc_info:
        build_classifier_service_from_manifest(manifest_path, runtime_builder=runtime_builder)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "CLASSIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"runtime_code": "CLASSIFIER_RUNTIME_BUILD_FAILED"}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
    assert "0.12345" not in rendered


def test_manifest_failure_type_is_kept_private_to_factory(tmp_path):
    missing_manifest = tmp_path / "missing.json"

    with pytest.raises(ClassifierServiceBuildError) as exc_info:
        build_classifier_service_from_manifest(missing_manifest)

    assert not isinstance(exc_info.value, ClassifierManifestLoadError)
