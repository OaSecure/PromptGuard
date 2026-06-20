from app.ml.verifier import (
    RobertaVerificationCandidate,
    RobertaVerificationRequest,
    VerifierArtifactRef,
)
from app.ml.verifier.runtime import LabelDefinition, RobertaVerifierRuntime


class FakePairScorer:
    def __init__(self, scores: list[float] | Exception) -> None:
        self.scores = scores
        self.seen_pair_texts: list[str] = []

    def score_positive_probabilities(self, pair_texts: list[str], *, max_length_tokens: int) -> list[float]:
        if isinstance(self.scores, Exception):
            raise self.scores
        self.seen_pair_texts = pair_texts
        return self.scores


def artifact() -> VerifierArtifactRef:
    return VerifierArtifactRef(
        artifact_id="context_lr_roberta_best_v205",
        model_version="klue-roberta-verifier-v204",
        runtime_version="context_lr_roberta_best_v205",
    )


def candidate(*, label: str = "SECRET_CREDENTIAL_CONTEXT", text: str | None = "actual secret token abc123") -> RobertaVerificationCandidate:
    return RobertaVerificationCandidate(segment_id="segment-1", candidate_label=label, text=text)


def request(*, candidates: list[RobertaVerificationCandidate] | None = None) -> RobertaVerificationRequest:
    return RobertaVerificationRequest(
        input_id="input-1",
        candidates=candidates if candidates is not None else [candidate()],
        artifact=artifact(),
    )


def runtime(scorer: FakePairScorer, *, threshold: float = 0.475, chunk_chars: int = 200) -> RobertaVerifierRuntime:
    return RobertaVerifierRuntime(
        pair_scorer=scorer,
        label_definitions={
            "SECRET_CREDENTIAL_CONTEXT": LabelDefinition(
                positive="YES when an actual credential appears.",
                negative="NO for placeholder-only examples.",
                boundary="Filled value is decisive.",
            )
        },
        thresholds={"SECRET_CREDENTIAL_CONTEXT": threshold},
        model_version="klue-roberta-verifier-v204",
        max_length_tokens=384,
        chunk_chars=chunk_chars,
        chunk_overlap=5,
        max_chunks=3,
    )


def test_roberta_runtime_confirms_candidate_when_score_meets_threshold():
    scorer = FakePairScorer([0.8])

    result = runtime(scorer).verify(request())

    assert result.failure is None
    assert [(item.candidate_label, item.verifier_status, item.accepted, item.confidence) for item in result.verifications] == [
        ("SECRET_CREDENTIAL_CONTEXT", "confirmed", True, 0.8)
    ]
    assert "Label: SECRET_CREDENTIAL_CONTEXT" in scorer.seen_pair_texts[0]
    assert "YES when an actual credential appears." in scorer.seen_pair_texts[0]
    assert "actual secret token abc123" in scorer.seen_pair_texts[0]


def test_roberta_runtime_rejects_candidate_when_score_is_below_threshold():
    result = runtime(FakePairScorer([0.3])).verify(request())

    assert result.failure is None
    assert result.verifications[0].verifier_status == "rejected"
    assert result.verifications[0].accepted is False
    assert result.verifications[0].confidence == 0.3


def test_roberta_runtime_uses_highest_chunk_score():
    long_text = "first chunk has context " + ("x" * 60)
    scorer = FakePairScorer([0.2, 0.77, 0.4])

    result = runtime(scorer, chunk_chars=20).verify(request(candidates=[candidate(text=long_text)]))

    assert len(scorer.seen_pair_texts) == 3
    assert result.verifications[0].verifier_status == "confirmed"
    assert result.verifications[0].confidence == 0.77


def test_roberta_runtime_marks_uncertain_when_label_definition_is_missing():
    result = runtime(FakePairScorer([0.8])).verify(request(candidates=[candidate(label="MISSING_CONTEXT")]))

    assert result.failure is None
    assert result.verifications[0].candidate_label == "MISSING_CONTEXT"
    assert result.verifications[0].verifier_status == "uncertain"
    assert result.verifications[0].accepted is False
    assert result.verifications[0].failure is None


def test_roberta_runtime_fails_candidate_when_text_is_unavailable_without_leaking_text():
    result = runtime(FakePairScorer([0.8])).verify(request(candidates=[candidate(text="  ")]))

    assert result.failure is None
    assert result.verifications[0].verifier_status == "failed"
    assert result.verifications[0].accepted is False
    assert result.verifications[0].failure is not None
    assert result.verifications[0].failure.code == "VERIFIER_TEXT_UNAVAILABLE"
    assert "actual secret" not in str(result.model_dump())


def test_roberta_runtime_fails_closed_when_scorer_raises_without_sensitive_message():
    result = runtime(FakePairScorer(RuntimeError("SENSITIVE_PROMPT_SENTINEL 0.9876"))).verify(request())

    assert result.verifications == []
    assert result.failure is not None
    assert result.failure.code == "VERIFIER_MODEL_FAILED"
    assert "SENSITIVE_PROMPT_SENTINEL" not in str(result.model_dump())
    assert "0.9876" not in str(result.model_dump())
