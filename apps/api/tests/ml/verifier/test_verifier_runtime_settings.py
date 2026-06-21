from pathlib import Path

from app.core.config import Settings
from app.ml.verifier import BuiltVerifierService, RobertaVerifierService, VerifierArtifactRef, VerifierServiceBuildError
from app.routes import analyze as analyze_route


class FakeVerifierRuntime:
    def verify(self, request):
        return None


def fake_bundle() -> BuiltVerifierService:
    return BuiltVerifierService(
        service=RobertaVerifierService(FakeVerifierRuntime()),
        artifact=VerifierArtifactRef(
            artifact_id="context_roberta_verifier_v205",
            model_version="roberta-verifier-test",
            runtime_version="roberta-verifier-runtime-test",
        ),
    )


def test_verifier_runtime_settings_default_to_disabled_without_manifest(monkeypatch):
    monkeypatch.delenv("PROMPTGUARD_VERIFIER_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("PROMPTGUARD_VERIFIER_MANIFEST_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.verifier_runtime_enabled is False
    assert settings.verifier_manifest_path == ""
    assert settings.verifier_manifest_path_value() is None


def test_verifier_runtime_settings_read_enabled_manifest_path_from_env_aliases():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_VERIFIER_RUNTIME_ENABLED="true",
        PROMPTGUARD_VERIFIER_MANIFEST_PATH="/opt/promptguard/models/context_roberta_verifier_v205_manifest.json",
    )

    assert settings.verifier_runtime_enabled is True
    assert settings.verifier_manifest_path_value() == Path(
        "/opt/promptguard/models/context_roberta_verifier_v205_manifest.json"
    )


def test_analyze_verifier_provider_does_not_build_when_disabled():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=False,
        PROMPTGUARD_VERIFIER_MANIFEST_PATH="SENSITIVE_FILENAME_SENTINEL.json",
    )

    def forbidden_builder(path):
        raise AssertionError(f"builder should not be called with {path}")

    config = analyze_route._build_analyze_verifier_config_from_settings(settings, builder=forbidden_builder)

    assert config is None


def test_analyze_verifier_provider_reports_missing_manifest_without_calling_builder():
    settings = Settings(_env_file=None, PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=True)

    def forbidden_builder(path):
        raise AssertionError(f"builder should not be called with {path}")

    config = analyze_route._build_analyze_verifier_config_from_settings(settings, builder=forbidden_builder)

    assert config is None


def test_analyze_verifier_provider_builds_config_from_settings():
    seen_paths: list[Path] = []
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=True,
        PROMPTGUARD_VERIFIER_MANIFEST_PATH="/opt/promptguard/models/context_roberta_verifier_v205_manifest.json",
    )

    def builder(path):
        seen_paths.append(path)
        return fake_bundle()

    config = analyze_route._build_analyze_verifier_config_from_settings(settings, builder=builder)

    assert config is not None
    assert config.artifact == fake_bundle().artifact
    assert isinstance(config.service, RobertaVerifierService)
    assert seen_paths == [Path("/opt/promptguard/models/context_roberta_verifier_v205_manifest.json")]


def test_analyze_verifier_provider_suppresses_build_failure_sensitive_values():
    settings = Settings(
        _env_file=None,
        PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=True,
        PROMPTGUARD_VERIFIER_MANIFEST_PATH="C:/private/SENSITIVE_FILENAME_SENTINEL.json",
    )

    def failing_builder(path):
        raise VerifierServiceBuildError(
            code="VERIFIER_SERVICE_BUILD_FAILED",
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

    config = analyze_route._build_analyze_verifier_config_from_settings(settings, builder=failing_builder)

    assert config is None


def test_env_example_documents_verifier_runtime_settings():
    env_example = Path(__file__).resolve().parents[5] / ".env.example"
    text = env_example.read_text(encoding="utf-8")

    assert "PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=false" in text
    assert "PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_roberta_verifier_manifest.json" in text
