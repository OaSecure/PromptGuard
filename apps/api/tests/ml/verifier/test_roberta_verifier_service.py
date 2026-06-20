from app.atoms.models import PipelineFailure
from app.ml.classifier import SegmentClassificationCandidate, SegmentClassificationResult
from app.ml.verifier import (
    RobertaVerificationRequest,
    RobertaVerificationResult,
    RobertaVerifierService,
    VerifierArtifactRef,
    build_verification_request_from_classifier,
)


class RecordingVerifierModel:
    def __init__(self, result: RobertaVerificationResult | None = None, raises: Exception | None = None) -> None:
        self.result = result
        self.raises = raises
        self.requests: list[RobertaVerificationRequest] = []

    def verify(self, request: RobertaVerificationRequest) -> RobertaVerificationResult:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        assert self.result is not None
        return self.result


def classifier_candidate(segment_id: str = "segment-1", label: str = "secret") -> SegmentClassificationCandidate:
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


def request_from_candidate(candidate: SegmentClassificationCandidate | None = None, *, include_candidate: bool = True) -> RobertaVerificationRequest:
    candidates = [candidate or classifier_candidate()] if include_candidate else []
    classification = SegmentClassificationResult(input_id="input-1", candidates=candidates)
    return build_verification_request_from_classifier(input_id="input-1", classification=classification, artifact=artifact())


def test_roberta_verifier_service_skips_model_without_lr_candidate():
    model = RecordingVerifierModel(result=RobertaVerificationResult(input_id="input-1"))

    result = RobertaVerifierService(model).verify(request_from_candidate(include_candidate=False))

    assert result.failure is None
    assert result.verifications == []
    assert model.requests == []


def test_roberta_verifier_service_accepts_lr_candidate_pairs_only():
    model = RecordingVerifierModel(
        result=RobertaVerificationResult(
            input_id="input-1",
            verifications=[
                {
                    "segment_id": "segment-1",
                    "candidate_label": "secret",
                    "verifier_status": "confirmed",
                    "accepted": True,
                    "confidence": 0.92,
                    "verifier_model_version": "klue-roberta-verifier-v1",
                }
            ],
        )
    )

    result = RobertaVerifierService(model).verify(request_from_candidate())

    assert result.failure is None
    assert [(item.segment_id, item.candidate_label, item.verifier_status) for item in result.verifications] == [
        ("segment-1", "secret", "confirmed")
    ]
    assert len(model.requests) == 1


def test_roberta_verifier_service_rejects_new_label_from_model():
    model = RecordingVerifierModel(
        result=RobertaVerificationResult(
            input_id="input-1",
            verifications=[
                {
                    "segment_id": "segment-1",
                    "candidate_label": "credential",
                    "verifier_status": "confirmed",
                    "accepted": True,
                    "confidence": 0.92,
                    "verifier_model_version": "klue-roberta-verifier-v1",
                }
            ],
        )
    )

    result = RobertaVerifierService(model).verify(request_from_candidate())

    assert result.verifications == []
    assert result.failure == PipelineFailure(code="VERIFIER_SCOPE_VIOLATION", message="verifier returned a non-candidate segment-label pair")


def test_roberta_verifier_service_fails_closed_on_model_exception():
    result = RobertaVerifierService(RecordingVerifierModel(raises=RuntimeError("boom"))).verify(request_from_candidate())

    assert result.verifications == []
    assert result.failure == PipelineFailure(code="VERIFIER_MODEL_FAILED", message="verifier model failed closed")


def test_roberta_verifier_timeout_status_is_not_action_or_allow():
    model = RecordingVerifierModel(
        result=RobertaVerificationResult(
            input_id="input-1",
            verifications=[
                {
                    "segment_id": "segment-1",
                    "candidate_label": "secret",
                    "verifier_status": "timeout",
                    "accepted": False,
                    "verifier_model_version": "klue-roberta-verifier-v1",
                }
            ],
        )
    )

    result = RobertaVerifierService(model).verify(request_from_candidate())

    assert result.failure is None
    assert result.verifications[0].verifier_status == "timeout"
    assert result.verifications[0].accepted is False
    assert "action" not in result.model_dump()
