import json
import os
from pathlib import Path

import pytest
from app.routes import analyze as analyze_route

from tests.contract.current_behavior.test_analyze_golden import client_for, payload, project_rows, text
from tests.test_analyze import _bearer_header


@pytest.mark.skipif(os.getenv("RUN_REAL_CONTEXT_MODEL_TESTS") != "1", reason="real context model route smoke is opt-in")
def test_public_analyze_route_runs_real_context_models_through_queue(monkeypatch):
    artifact_root_env = os.getenv("PROMPTGUARD_TEST_CONTEXT_ARTIFACT_DIR")
    if not artifact_root_env:
        pytest.skip("PROMPTGUARD_TEST_CONTEXT_ARTIFACT_DIR is not configured")

    artifact_root = Path(artifact_root_env)
    manifest_path = artifact_root / "models" / "context_lr_roberta_active_best_f1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("PromptGuard context manifest is not available")

    _clear_runtime_caches()
    monkeypatch.setenv("PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PROMPTGUARD_CLASSIFIER_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("PROMPTGUARD_VERIFIER_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PROMPTGUARD_VERIFIER_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_ENABLED", "true")
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_MAX_WORKERS", "1")
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_MAX_QUEUE_SIZE", "2")
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS", "120000")

    client, session = client_for([])
    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header("10000000-0000-0000-0000-000000000001"),
        json=payload([text("input_1", "Credential exposure risk appears in deployment automation notes.")]),
    )

    body = response.json()
    storage = project_rows(session)
    serialized_body = json.dumps(body, ensure_ascii=False)
    serialized_storage = json.dumps(storage, default=str, ensure_ascii=False)

    assert response.status_code == 200
    assert body["action"] == "Warn"
    assert body["requires_user_confirmation"] is True
    assert body["detections"] == []
    assert body["input_results"][0]["decision_basis"] == "no_detection"
    assert storage["event"]["action"] == "WARN"
    assert storage["event"]["risk_score"] == 0
    assert storage["event"]["risk_level"] == "low"
    assert storage["inputs"][0]["content_scanned"] is True
    assert "Credential exposure risk" not in serialized_body
    assert "Credential exposure risk" not in serialized_storage
    assert "embedding" not in serialized_body.casefold()
    assert "logit" not in serialized_body.casefold()
    assert "classifier_score" not in serialized_body.casefold()
    assert "classifier_score" not in serialized_storage.casefold()
    assert "exact_score" not in serialized_body.casefold()
    assert "exact_score" not in serialized_storage.casefold()


def _clear_runtime_caches() -> None:
    analyze_route.get_settings.cache_clear()
    analyze_route._cached_classifier_runtime_provider.cache_clear()
    analyze_route._cached_analyze_verifier_config.cache_clear()
    analyze_route._cached_ml_inference_queue.cache_clear()
