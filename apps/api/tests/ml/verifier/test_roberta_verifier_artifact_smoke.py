import os
from pathlib import Path

import pytest

from app.ml.verifier import RobertaVerificationCandidate, RobertaVerificationRequest
from app.ml.verifier.factory import build_verifier_service_from_manifest


def test_optional_real_roberta_artifact_smoke_loads_when_configured():
    artifact_dir = os.getenv("PROMPTGUARD_TEST_VERIFIER_ARTIFACT_DIR")
    if not artifact_dir:
        pytest.skip("PROMPTGUARD_TEST_VERIFIER_ARTIFACT_DIR is not configured")

    artifact_root = Path(artifact_dir)
    manifest_path = artifact_root / "models" / "context_lr_roberta_best_v205_manifest.json"

    bundle = build_verifier_service_from_manifest(manifest_path, artifact_root=artifact_root)
    result = bundle.service.verify(
        RobertaVerificationRequest(
            input_id="input-1",
            candidates=[
                RobertaVerificationCandidate(
                    segment_id="segment-1",
                    candidate_label="SECRET_CREDENTIAL_CONTEXT",
                    text="api_key = 'pg_live_1234567890abcdef'",
                )
            ],
            artifact=bundle.artifact,
            timeout_ms=3000,
        )
    )

    assert result.failure is None
    assert len(result.verifications) == 1
    assert result.verifications[0].candidate_label == "SECRET_CREDENTIAL_CONTEXT"
    assert result.verifications[0].verifier_status in {"confirmed", "rejected"}
