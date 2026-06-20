from typing import Any

from app.ml.classifier.models import SegmentClassificationCandidate, SegmentClassificationResult

SIGNAL_LABEL_GROUPS = ("risk", "suppressor", "code", "pii_relevance", "other")


def project_classification_result_metadata(result: SegmentClassificationResult) -> dict[str, Any]:
    return {
        "candidate_count": len(result.candidates),
        "candidates": [_project_candidate_metadata(candidate) for candidate in result.candidates],
        "failure": _project_failure_metadata(result),
    }


def project_classification_signal_summary(result: SegmentClassificationResult) -> dict[str, Any]:
    """Return action-neutral classifier signals without raw scores or input content."""
    label_groups = _empty_label_groups()

    for candidate in result.candidates:
        label_groups[_label_group(candidate.label)] += 1

    return {
        "candidate_count": len(result.candidates),
        "has_candidates": bool(result.candidates),
        "highest_score_bucket": _highest_score_bucket(result.candidates),
        "label_groups": label_groups,
        "failure": _project_failure_metadata(result),
    }


def _project_candidate_metadata(candidate: SegmentClassificationCandidate) -> dict[str, Any]:
    return {
        "segment_id": candidate.segment_id,
        "label": candidate.label,
        "score_bucket": _score_bucket(candidate.score),
        "threshold": candidate.threshold,
        "artifact_id": candidate.artifact_id,
        "runtime_version": candidate.runtime_version,
    }


def _score_bucket(score: float) -> str:
    if score >= 0.9:
        return "very_high"
    if score >= 0.75:
        return "high"
    return "candidate"


def _highest_score_bucket(candidates: list[SegmentClassificationCandidate]) -> str | None:
    if not candidates:
        return None
    return _score_bucket(max(candidate.score for candidate in candidates))


def _empty_label_groups() -> dict[str, int]:
    return {group: 0 for group in SIGNAL_LABEL_GROUPS}


def _label_group(label: str) -> str:
    normalized = label.lower()
    if _contains_any(normalized, ("secret", "credential", "token", "key", "password", "private")):
        return "risk"
    if _contains_any(normalized, ("safe", "synthetic", "dummy", "example", "test")):
        return "suppressor"
    if _contains_any(normalized, ("code", "source", "repository", "snippet")):
        return "code"
    if _contains_any(normalized, ("pii", "personal", "email", "phone", "ssn", "rrn")):
        return "pii_relevance"
    return "other"


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _project_failure_metadata(result: SegmentClassificationResult) -> dict[str, Any] | None:
    if result.failure is None:
        return None
    return {"code": result.failure.code}
