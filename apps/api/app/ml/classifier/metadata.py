from typing import Any

from app.ml.classifier.models import SegmentClassificationCandidate, SegmentClassificationResult


def project_classification_result_metadata(result: SegmentClassificationResult) -> dict[str, Any]:
    return {
        "candidate_count": len(result.candidates),
        "candidates": [_project_candidate_metadata(candidate) for candidate in result.candidates],
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


def _project_failure_metadata(result: SegmentClassificationResult) -> dict[str, Any] | None:
    if result.failure is None:
        return None
    return {"code": result.failure.code}
