import math
from dataclasses import dataclass
from typing import Protocol

from app.atoms.models import PipelineFailure
from app.ml.verifier.models import (
    RobertaVerificationCandidate,
    RobertaVerificationEvidence,
    RobertaVerificationRequest,
    RobertaVerificationResult,
)


class VerifierPairScorer(Protocol):
    def score_positive_probabilities(self, pair_texts: list[str], *, max_length_tokens: int) -> list[float]:
        ...


@dataclass(frozen=True)
class LabelDefinition:
    positive: str
    negative: str
    boundary: str


class RobertaVerifierRuntime:
    def __init__(
        self,
        *,
        pair_scorer: VerifierPairScorer,
        label_definitions: dict[str, LabelDefinition],
        thresholds: dict[str, float],
        model_version: str,
        max_length_tokens: int = 384,
        chunk_chars: int = 900,
        chunk_overlap: int = 120,
        max_chunks: int = 8,
    ) -> None:
        self._pair_scorer = pair_scorer
        self._label_definitions = label_definitions
        self._thresholds = thresholds
        self._model_version = model_version
        self._max_length_tokens = max_length_tokens
        self._chunk_chars = chunk_chars
        self._chunk_overlap = chunk_overlap
        self._max_chunks = max_chunks

    def verify(self, request: RobertaVerificationRequest) -> RobertaVerificationResult:
        verifications: list[RobertaVerificationEvidence] = []

        for candidate in request.candidates:
            if candidate.text is None or not candidate.text.strip():
                verifications.append(self._candidate_failed(candidate, "VERIFIER_TEXT_UNAVAILABLE", "verifier text is unavailable"))
                continue

            label_definition = self._label_definitions.get(candidate.candidate_label)
            threshold = self._thresholds.get(candidate.candidate_label)
            if label_definition is None or threshold is None:
                verifications.append(self._uncertain(candidate, "VERIFIER_LABEL_DEFINITION_MISSING"))
                continue

            pair_texts = [
                _format_pair_text(candidate.candidate_label, label_definition, chunk)
                for chunk in _chunk_text(candidate.text, chunk_chars=self._chunk_chars, chunk_overlap=self._chunk_overlap, max_chunks=self._max_chunks)
            ]
            if not pair_texts:
                verifications.append(self._candidate_failed(candidate, "VERIFIER_TEXT_UNAVAILABLE", "verifier text is unavailable"))
                continue

            try:
                scores = self._pair_scorer.score_positive_probabilities(pair_texts, max_length_tokens=self._max_length_tokens)
            except Exception:
                return RobertaVerificationResult(
                    input_id=request.input_id,
                    failure=PipelineFailure(code="VERIFIER_MODEL_FAILED", message="verifier model failed closed"),
                )

            if len(scores) != len(pair_texts) or any(not math.isfinite(score) or score < 0.0 or score > 1.0 for score in scores):
                return RobertaVerificationResult(
                    input_id=request.input_id,
                    failure=PipelineFailure(code="VERIFIER_INVALID_SCORE", message="verifier score is invalid"),
                )

            confidence = max(float(score) for score in scores)
            confirmed = confidence >= threshold
            verifications.append(
                RobertaVerificationEvidence(
                    segment_id=candidate.segment_id,
                    candidate_label=candidate.candidate_label,
                    verifier_status="confirmed" if confirmed else "rejected",
                    accepted=confirmed,
                    confidence=confidence,
                    reason_code_candidates=["VERIFIER_CONFIRMED" if confirmed else "VERIFIER_REJECTED"],
                    verifier_model_version=self._model_version,
                )
            )

        return RobertaVerificationResult(input_id=request.input_id, verifications=verifications)

    def _uncertain(self, candidate: RobertaVerificationCandidate, reason_code: str) -> RobertaVerificationEvidence:
        return RobertaVerificationEvidence(
            segment_id=candidate.segment_id,
            candidate_label=candidate.candidate_label,
            verifier_status="uncertain",
            accepted=False,
            reason_code_candidates=[reason_code],
            verifier_model_version=self._model_version,
        )

    def _candidate_failed(self, candidate: RobertaVerificationCandidate, code: str, message: str) -> RobertaVerificationEvidence:
        return RobertaVerificationEvidence(
            segment_id=candidate.segment_id,
            candidate_label=candidate.candidate_label,
            verifier_status="failed",
            accepted=False,
            reason_code_candidates=[code],
            verifier_model_version=self._model_version,
            failure=PipelineFailure(code=code, message=message),
        )


def _format_pair_text(label: str, definition: LabelDefinition, text: str) -> str:
    return "\n".join(
        [
            f"Label: {label}",
            f"YES: {definition.positive}",
            f"NO: {definition.negative}",
            f"Boundary: {definition.boundary}",
            "",
            "Text:",
            text,
        ]
    )


def _chunk_text(text: str, *, chunk_chars: int, chunk_overlap: int, max_chunks: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    chunk_size = max(1, chunk_chars)
    overlap = min(max(0, chunk_overlap), chunk_size - 1)
    chunks: list[str] = []
    start = 0
    while start < len(stripped) and len(chunks) < max_chunks:
        end = min(len(stripped), start + chunk_size)
        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(stripped):
            break
        start = end - overlap
    return chunks
