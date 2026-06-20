import json
from pathlib import Path

import pytest

from app.ml.verifier import RobertaVerificationRequest
from app.ml.verifier.factory import (
    BuiltVerifierService,
    VerifierRuntimeBuildError,
    VerifierServiceBuildError,
    build_roberta_verifier_runtime,
    build_verifier_service_from_manifest,
)
from app.ml.verifier.loader import RobertaVerifierLoadError
from app.ml.verifier.manifest import VerifierManifestLoadError
from app.ml.verifier.runtime import RobertaVerifierRuntime


class FakePairScorer:
    def __init__(self) -> None:
        self.seen_pair_texts: list[str] = []

    def score_positive_probabilities(self, pair_texts: list[str], *, max_length_tokens: int) -> list[float]:
        self.seen_pair_texts = pair_texts
        return [0.99 for _ in pair_texts]


class FakeRuntime:
    def __init__(self) -> None:
        self.seen_request: RobertaVerificationRequest | None = None

    def verify(self, request: RobertaVerificationRequest):
        self.seen_request = request
        from app.ml.verifier import RobertaVerificationResult

        return RobertaVerificationResult(input_id=request.input_id)


def write_manifest_bundle(tmp_path: Path) -> Path:
    models_dir = tmp_path / "models"
    verifier_dir = models_dir / "context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6"
    verifier_dir.mkdir(parents=True)
    manifest_path = models_dir / "context_lr_roberta_best_v205_manifest.json"

    (tmp_path / "context_target_labels.json").write_text(json.dumps({"target_labels": ["secret"]}), encoding="utf-8")
    (tmp_path / "context_label_definitions.json").write_text(
        json.dumps({"secret": {"positive": "yes", "negative": "no", "boundary": "boundary"}}),
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
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_roberta_verifier_runtime_factory_builds_runtime_from_loader():
    scorer = FakePairScorer()

    runtime = build_roberta_verifier_runtime(
        Path("model-dir"),
        label_definitions={"secret": {"positive": "yes", "negative": "no", "boundary": "boundary"}},
        thresholds={"secret": 0.475},
        model_version="model-v1",
        loader=lambda path: scorer,
    )

    assert isinstance(runtime, RobertaVerifierRuntime)
    assert runtime.verify(
        RobertaVerificationRequest(
            input_id="input-1",
            candidates=[{"segment_id": "s1", "candidate_label": "secret", "text": "secret value"}],
            artifact={"artifact_id": "artifact", "model_version": "model-v1", "runtime_version": "runtime"},
        )
    ).verifications[0].accepted is True


def test_roberta_verifier_runtime_factory_wraps_loader_failure_without_sensitive_values():
    def failing_loader(path: Path):
        raise RobertaVerifierLoadError(
            "VERIFIER_ARTIFACT_LOAD_FAILED",
            "verifier artifact is invalid",
            metadata={"raw_prompt": "SENSITIVE_PROMPT_SENTINEL", "original_filename": "SENSITIVE_FILENAME_SENTINEL"},
        )

    with pytest.raises(VerifierRuntimeBuildError) as exc_info:
        build_roberta_verifier_runtime(
            Path("SENSITIVE_FILENAME_SENTINEL"),
            label_definitions={"secret": {"positive": "yes", "negative": "no", "boundary": "boundary"}},
            thresholds={"secret": 0.475},
            model_version="model-v1",
            loader=failing_loader,
        )

    rendered = str(exc_info.value)
    assert exc_info.value.code == "VERIFIER_RUNTIME_BUILD_FAILED"
    assert exc_info.value.metadata == {"loader_code": "VERIFIER_ARTIFACT_LOAD_FAILED"}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_manifest_backed_verifier_service_factory_builds_service_bundle(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)
    runtime = FakeRuntime()
    seen_paths: list[Path] = []

    def runtime_builder(path: Path, **kwargs):
        seen_paths.append(path)
        return runtime

    bundle = build_verifier_service_from_manifest(manifest_path, runtime_builder=runtime_builder)

    assert isinstance(bundle, BuiltVerifierService)
    assert seen_paths == [tmp_path / "models" / "context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6"]
    assert bundle.artifact.artifact_id == "context_lr_roberta_best_v205"
    assert bundle.artifact.model_version == "context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6"


def test_manifest_backed_verifier_service_factory_wraps_manifest_failure_without_sensitive_values(tmp_path):
    missing_manifest = tmp_path / "SENSITIVE_FILENAME_SENTINEL_manifest.json"

    with pytest.raises(VerifierServiceBuildError) as exc_info:
        build_verifier_service_from_manifest(missing_manifest)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "VERIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"manifest_code": "VERIFIER_MANIFEST_NOT_FOUND"}
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered


def test_manifest_backed_verifier_service_factory_wraps_runtime_failure_without_sensitive_values(tmp_path):
    manifest_path = write_manifest_bundle(tmp_path)

    def runtime_builder(path: Path, **kwargs):
        raise VerifierRuntimeBuildError(
            code="VERIFIER_RUNTIME_BUILD_FAILED",
            message="verifier runtime could not be built",
            metadata={"raw_prompt": "SENSITIVE_PROMPT_SENTINEL"},
        )

    with pytest.raises(VerifierServiceBuildError) as exc_info:
        build_verifier_service_from_manifest(manifest_path, runtime_builder=runtime_builder)

    rendered = str(exc_info.value)
    assert exc_info.value.code == "VERIFIER_SERVICE_BUILD_FAILED"
    assert exc_info.value.metadata == {"runtime_code": "VERIFIER_RUNTIME_BUILD_FAILED"}
    assert "SENSITIVE_PROMPT_SENTINEL" not in rendered


def test_manifest_failure_type_is_kept_private_to_factory(tmp_path):
    with pytest.raises(VerifierServiceBuildError) as exc_info:
        build_verifier_service_from_manifest(tmp_path / "missing.json")

    assert not isinstance(exc_info.value, VerifierManifestLoadError)
