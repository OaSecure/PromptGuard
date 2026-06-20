import pytest
from pydantic import ValidationError

from app.atoms.models import PipelineFailure
from app.ml.classifier import SegmentClassificationCandidate, SegmentClassificationResult
from app.ml.verifier import (
    RobertaVerificationCandidate,
    RobertaVerificationRequest,
    RobertaVerificationResult,
    RobertaVerificationStatus,
    VerifierArtifactRef,
    build_verification_request_from_classifier,
)


def candidate(segment_id: str = "segment-1", label: str = "secret") -> SegmentClassificationCandidate:
    return SegmentClassificationCandidate(
        segment_id=segment_id,
        label=label,
        score=0.91,
        threshold=0.575,
        artifact_id="lr-v205",
        runtime_version="lr-runtime-v1",
    )


def artifact() -> VerifierArtifactRef:
    return VerifierArtifactRef(
        artifact_id="context-verifier-v1",
        model_version="klue-roberta-verifier-v1",
        runtime_version="roberta-verifier-runtime-v1",
    )


def test_verifier_request_is_built_only_from_classifier_candidates():
    request = build_verification_request_from_classifier(
        input_id="input-1",
        classification=SegmentClassificationResult(input_id="input-1", candidates=[candidate()]),
        artifact=artifact(),
        timeout_ms=3000,
    )

    assert request.input_id == "input-1"
    assert request.timeout_ms == 3000
    assert request.candidates == [
        RobertaVerificationCandidate(
            segment_id="segment-1",
            candidate_label="secret",
            classifier_artifact_id="lr-v205",
            classifier_runtime_version="lr-runtime-v1",
        )
    ]
    assert not hasattr(request.candidates[0], "score")
    assert request.candidates[0].text is None
    assert "text" not in request.candidates[0].model_dump()


def test_verifier_candidate_text_is_runtime_only_and_excluded_from_dumps():
    request = build_verification_request_from_classifier(
        input_id="input-1",
        classification=SegmentClassificationResult(input_id="input-1", candidates=[candidate()]),
        artifact=artifact(),
        candidate_text_by_segment_id={"segment-1": "SENSITIVE_PROMPT_SENTINEL"},
    )

    assert request.candidates[0].text == "SENSITIVE_PROMPT_SENTINEL"
    assert "text" not in request.candidates[0].model_dump()
    assert "SENSITIVE_PROMPT_SENTINEL" not in str(request.model_dump())


def test_verifier_request_skips_when_classifier_has_no_candidate():
    request = build_verification_request_from_classifier(
        input_id="input-1",
        classification=SegmentClassificationResult(input_id="input-1"),
        artifact=artifact(),
    )

    assert request.candidates == []


def test_verifier_request_rejects_classifier_failure_with_candidates():
    with pytest.raises(ValueError, match="classifier failure"):
        build_verification_request_from_classifier(
            input_id="input-1",
            classification=SegmentClassificationResult(
                input_id="input-1",
                failure=PipelineFailure(code="CLASSIFIER_FAILED", message="classifier failed"),
            ),
            artifact=artifact(),
        )


def test_verifier_status_is_closed_enum_and_result_is_not_action():
    assert set(RobertaVerificationStatus.__args__) == {"confirmed", "rejected", "uncertain", "timeout", "failed"}

    result = RobertaVerificationResult(
        input_id="input-1",
        verifications=[
            {
                "segment_id": "segment-1",
                "candidate_label": "secret",
                "verifier_status": "confirmed",
                "accepted": True,
                "confidence": 0.9,
                "verifier_model_version": "klue-roberta-verifier-v1",
            }
        ],
    )

    payload = result.model_dump()
    assert "action" not in payload
    assert "reason_code" not in payload
    assert "user_notice" not in payload


def test_verifier_rejects_blank_identity_fields():
    with pytest.raises(ValidationError):
        RobertaVerificationRequest(input_id="", candidates=[RobertaVerificationCandidate(segment_id="s1", candidate_label="secret")], artifact=artifact())

