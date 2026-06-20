from app.ml.verifier import RobertaVerificationResult, project_verification_signal_summary


def test_verifier_summary_uses_safe_allowlist_without_raw_values():
    result = RobertaVerificationResult(
        input_id="input-SECRET-RAW-PROMPT",
        verifications=[
            {
                "segment_id": "segment-1",
                "candidate_label": "secret",
                "verifier_status": "confirmed",
                "accepted": True,
                "confidence": 0.92345,
                "verifier_model_version": "klue-roberta-verifier-v1",
                "reason_code_candidates": ["possible_secret_context"],
            }
        ],
    )

    payload = project_verification_signal_summary(result)
    payload_text = str(payload)

    assert set(payload) == {
        "verification_count",
        "accepted_count",
        "status_counts",
        "labels",
        "highest_confidence_bucket",
        "verifier_model_versions",
        "failure",
    }
    assert "SECRET-RAW-PROMPT" not in payload_text
    assert "0.92345" not in payload_text
    assert "logit" not in payload_text.lower()
    assert "text" not in payload_text.lower()
    assert "vector" not in payload_text.lower()
    assert "action" not in payload_text.lower()
    assert payload["highest_confidence_bucket"] == "high"

