from typing import Any

from app.ml.verifier.models import RobertaVerificationEvidence, RobertaVerificationResult

VERIFIER_STATUSES = ("confirmed", "rejected", "uncertain", "timeout", "failed")


def project_verification_signal_summary(result: RobertaVerificationResult) -> dict[str, Any]:
    return {
        "verification_count": len(result.verifications),
        "accepted_count": sum(1 for item in result.verifications if item.accepted),
        "status_counts": _status_counts(result.verifications),
        "labels": sorted({item.candidate_label for item in result.verifications}),
        "highest_confidence_bucket": _highest_confidence_bucket(result.verifications),
        "verifier_model_versions": sorted({item.verifier_model_version for item in result.verifications}),
        "failure": _project_failure_metadata(result),
    }


def _status_counts(verifications: list[RobertaVerificationEvidence]) -> dict[str, int]:
    counts = {status: 0 for status in VERIFIER_STATUSES}
    for item in verifications:
        counts[item.verifier_status] += 1
    return counts


def _highest_confidence_bucket(verifications: list[RobertaVerificationEvidence]) -> str | None:
    confidences = [item.confidence for item in verifications if item.confidence is not None]
    if not confidences:
        return None
    return _confidence_bucket(max(confidences))


def _confidence_bucket(confidence: float) -> str:
    if confidence >= 0.95:
        return "very_high"
    if confidence >= 0.75:
        return "high"
    return "candidate"


def _project_failure_metadata(result: RobertaVerificationResult) -> dict[str, Any] | None:
    if result.failure is None:
        return None
    return {"code": result.failure.code}

