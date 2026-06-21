from pathlib import Path

from app.core.config import Settings
from app.ml.classifier import ClassifierArtifactRef, ClassifierService
from app.ml.classifier.factory import BuiltClassifierService, ClassifierServiceBuildError
from app.ml.classifier.factory import build_classifier_service_from_settings


class FakeRuntime:
    def classify(self, request):
        return None


def fake_bundle() -> BuiltClassifierService:
    return BuiltClassifierService(
        service=ClassifierService(FakeRuntime()),
        artifact=ClassifierArtifactRef(
            artifact_id="context_lr_roberta_best_v205",
            manifest_version="context_lr_roberta_best_v205",
            runtime_version="context_lr_roberta_best_v205",
            target_labels=["secret"],
            candidate_threshold=0.575,
            embedding_model_version="roberta-base",
        ),
    )


def render_provider_result(result) -> str:
    return repr(result) + repr(result.failure) + repr(result.failure.metadata if result.failure else {})


def test_classifier_runtime_settings_default_to_disabled_without_manifest(monkeypatch):
    monkeypatch.delenv("PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.classifier_runtime_enabled is False
    assert settings.classifier_manifest_path == ""
    assert settings.classifier_manifest_path_value() is None


def test_classifier_runtime_settings_read_enabled_manifest_path_from_env_aliases():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED="true",
        PROMPTGUARD_CLASSIFIER_MANIFEST_PATH="/opt/promptguard/models/context_lr_roberta_best_v205_manifest.json",
    )

    assert settings.classifier_runtime_enabled is True
    assert settings.classifier_manifest_path_value() == Path(
        "/opt/promptguard/models/context_lr_roberta_best_v205_manifest.json"
    )


def test_classifier_provider_does_not_build_when_disabled():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=False,
        PROMPTGUARD_CLASSIFIER_MANIFEST_PATH="SENSITIVE_FILENAME_SENTINEL.json",
    )

    def forbidden_builder(path):
        raise AssertionError(f"builder should not be called with {path}")

    result = build_classifier_service_from_settings(settings, builder=forbidden_builder)

    assert result.available is False
    assert result.bundle is None
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_RUNTIME_DISABLED"
    assert "SENSITIVE_FILENAME_SENTINEL" not in render_provider_result(result)


def test_classifier_provider_reports_missing_manifest_without_calling_builder():
    settings = Settings(_env_file=None, PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=True)

    def forbidden_builder(path):
        raise AssertionError(f"builder should not be called with {path}")

    result = build_classifier_service_from_settings(settings, builder=forbidden_builder)

    assert result.available is False
    assert result.bundle is None
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_MANIFEST_NOT_CONFIGURED"
    assert result.failure.metadata == {"status": "unavailable"}


def test_classifier_provider_builds_service_bundle_from_settings():
    seen_paths: list[Path] = []
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=True,
        PROMPTGUARD_CLASSIFIER_MANIFEST_PATH="/opt/promptguard/models/context_lr_roberta_best_v205_manifest.json",
    )

    def builder(path):
        seen_paths.append(path)
        return fake_bundle()

    result = build_classifier_service_from_settings(settings, builder=builder)

    assert result.available is True
    assert result.failure is None
    assert result.bundle is not None
    assert result.bundle.artifact == fake_bundle().artifact
    assert isinstance(result.bundle.service, ClassifierService)
    assert seen_paths == [Path("/opt/promptguard/models/context_lr_roberta_best_v205_manifest.json")]


def test_classifier_provider_wraps_build_failure_without_sensitive_values():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=True,
        PROMPTGUARD_CLASSIFIER_MANIFEST_PATH="C:/private/SENSITIVE_FILENAME_SENTINEL.json",
    )

    def failing_builder(path):
        raise ClassifierServiceBuildError(
            code="CLASSIFIER_SERVICE_BUILD_FAILED",
            message="SENSITIVE_PROMPT_SENTINEL SENSITIVE_FILENAME_SENTINEL 0.12345",
            metadata={
                "raw_prompt": "SENSITIVE_PROMPT_SENTINEL",
                "file_content": "SENSITIVE_FILE_CONTENT_SENTINEL",
                "extracted_text": "SENSITIVE_EXTRACTED_TEXT_SENTINEL",
                "detected_raw_value": "SENSITIVE_DETECTED_RAW_VALUE_SENTINEL",
                "original_filename": "SENSITIVE_FILENAME_SENTINEL",
                "raw_score": "0.12345",
                "vector": "[0.12345, 0.67890]",
            },
        )

    result = build_classifier_service_from_settings(settings, builder=failing_builder)
    rendered = render_provider_result(result)

    assert result.available is False
    assert result.bundle is None
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_RUNTIME_UNAVAILABLE"
    assert result.failure.message == "classifier runtime unavailable"
    assert result.failure.metadata == {
        "status": "unavailable",
        "build_code": "CLASSIFIER_SERVICE_BUILD_FAILED",
    }
    for sentinel in [
        "SENSITIVE_PROMPT_SENTINEL",
        "SENSITIVE_FILE_CONTENT_SENTINEL",
        "SENSITIVE_EXTRACTED_TEXT_SENTINEL",
        "SENSITIVE_DETECTED_RAW_VALUE_SENTINEL",
        "SENSITIVE_FILENAME_SENTINEL",
        "0.12345",
        "0.67890",
    ]:
        assert sentinel not in rendered


def test_env_example_documents_classifier_runtime_settings():
    env_example = Path(__file__).resolve().parents[5] / ".env.example"
    text = env_example.read_text(encoding="utf-8")

    assert "PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=false" in text
    assert "PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_manifest.json" in text
