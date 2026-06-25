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


def test_verifier_summary_labels_include_only_accepted_confirmed_labels():
    result = RobertaVerificationResult(
        input_id="input-1",
        verifications=[
            {
                "segment_id": "segment-1",
                "candidate_label": "INTERNAL_OPERATION_CONTEXT",
                "verifier_status": "confirmed",
                "accepted": True,
                "confidence": 0.95,
                "verifier_model_version": "klue-roberta-verifier-v1",
            },
            {
                "segment_id": "segment-1",
                "candidate_label": "PERSONAL_DATA_CONTEXT",
                "verifier_status": "rejected",
                "accepted": False,
                "confidence": 0.12,
                "verifier_model_version": "klue-roberta-verifier-v1",
            },
        ],
    )

    payload = project_verification_signal_summary(result)

    assert payload["accepted_count"] == 1
    assert payload["status_counts"]["confirmed"] == 1
    assert payload["status_counts"]["rejected"] == 1
    assert payload["labels"] == ["INTERNAL_OPERATION_CONTEXT"]

