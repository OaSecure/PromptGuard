from typing import Any, Literal

from pydantic import BaseModel, Field

from .common import ReasonCode

PolicyAction = Literal["allow", "warn", "mask", "block"]
PolicySeverity = Literal["info", "low", "medium", "high", "critical"]
ConfigurablePolicyAction = Literal["allow", "warn", "block"]
UnsupportedMaskFallbackAction = Literal["warn", "block"]
ContextRiskStatus = Literal["disabled", "no_candidate", "candidate", "verified", "timeout", "failed"]

_BUCKET_RANK = {"candidate": 1, "high": 2, "very_high": 3}


class PolicyActionSettings(BaseModel):
    context_classifier_action: ConfigurablePolicyAction = "warn"
    content_not_scanned_action: ConfigurablePolicyAction = "warn"
    parser_or_ocr_failure_action: ConfigurablePolicyAction = "warn"
    empty_input_action: ConfigurablePolicyAction = "allow"
    unsupported_mask_fallback_action: UnsupportedMaskFallbackAction = "block"


class PolicyRuleEvidence(BaseModel):
    action: PolicyAction
    severity: PolicySeverity
    reason_code: ReasonCode = "INTERNAL_POLICY_REASON_UNMAPPED"
    masking_supported: bool = True


class PolicyInputEvidence(BaseModel):
    input_id: str
    content_scanned: bool


class ContextRiskEvidence(BaseModel):
    enabled: bool = False
    status: ContextRiskStatus = "disabled"
    candidate_count: int = 0
    accepted_count: int = 0
    labels: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    highest_score_bucket: str | None = None
    highest_confidence_bucket: str | None = None
    failure_code: str | None = None
    reason_code: ReasonCode = "NO_RISK_DETECTED"
    classifier_model_versions: list[str] = Field(default_factory=list)
    verifier_model_versions: list[str] = Field(default_factory=list)


class PolicyMlEvidence(BaseModel):
    classifier_enabled: bool = False
    classifier_has_candidates: bool = False
    classifier_failed: bool = False
    verifier_failed: bool = False
    verifier_summary_present: bool = False
    context: ContextRiskEvidence = Field(default_factory=ContextRiskEvidence)


class PolicyDecisionRequest(BaseModel):
    request_id: str
    input_ids: list[str]
    evidence_codes: list[ReasonCode] = Field(default_factory=list)
    rules: list[PolicyRuleEvidence] = Field(default_factory=list)
    inputs: list[PolicyInputEvidence] = Field(default_factory=list)
    ml: PolicyMlEvidence = Field(default_factory=PolicyMlEvidence)
    action_settings: PolicyActionSettings = Field(default_factory=PolicyActionSettings)


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason_code: ReasonCode
    severity: PolicySeverity


def build_context_risk_evidence(
    *,
    enabled: bool,
    classification_summaries: list[dict[str, Any]] | None = None,
    verifier_summaries: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
) -> ContextRiskEvidence:
    if not enabled:
        return ContextRiskEvidence()

    classification_summaries = classification_summaries or []
    verifier_summaries = verifier_summaries or []
    candidate_count = _summary_count(classification_summaries, "candidate_count")
    accepted_count = _summary_count(verifier_summaries, "accepted_count")
    status_counts = _merged_status_counts(verifier_summaries)
    failure_code = failure_code or _first_failure_code(classification_summaries, verifier_summaries)
    status, reason_code = _context_status_and_reason(
        candidate_count=candidate_count,
        accepted_count=accepted_count,
        status_counts=status_counts,
        failure_code=failure_code,
    )
    return ContextRiskEvidence(
        enabled=True,
        status=status,
        candidate_count=candidate_count,
        accepted_count=accepted_count,
        labels=_evidence_labels(verifier_summaries),
        status_counts=status_counts,
        highest_score_bucket=_max_bucket(summary.get("highest_score_bucket") for summary in classification_summaries),
        highest_confidence_bucket=_max_bucket(summary.get("highest_confidence_bucket") for summary in verifier_summaries),
        failure_code=failure_code,
        reason_code=reason_code,
        classifier_model_versions=_summary_string_values(classification_summaries, "classifier_model_versions"),
        verifier_model_versions=_summary_string_values(verifier_summaries, "verifier_model_versions"),
    )


def _context_status_and_reason(
    *,
    candidate_count: int,
    accepted_count: int,
    status_counts: dict[str, int],
    failure_code: str | None,
) -> tuple[ContextRiskStatus, ReasonCode]:
    if failure_code:
        if "TIMEOUT" in failure_code.upper():
            return "timeout", "RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT"
        return "failed", "RISK_CONTEXT_LR_ONLY_VERIFIER_FAILED"
    if accepted_count > 0:
        return "verified", "RISK_CONTEXT_VERIFIER_CONFIRMED"
    if candidate_count > 0:
        if status_counts.get("uncertain", 0) > 0:
            return "candidate", "RISK_CONTEXT_VERIFIER_UNCERTAIN"
        return "candidate", "RISK_CONTEXT_LR_ONLY"
    return "no_candidate", "NO_RISK_DETECTED"


def _merged_status_counts(summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        raw_counts = summary.get("status_counts")
        if not isinstance(raw_counts, dict):
            continue
        for key, value in raw_counts.items():
            if isinstance(key, str):
                counts[key] = counts.get(key, 0) + _safe_int(value)
    return counts


def _summary_count(summaries: list[dict[str, Any]], key: str) -> int:
    return sum(_safe_int(summary.get(key)) for summary in summaries)


def _evidence_labels(summaries: list[dict[str, Any]]) -> list[str]:
    return _summary_string_values(summaries, "labels")


def _summary_string_values(summaries: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({value for summary in summaries for value in _safe_string_list(summary.get(key))})


def _first_failure_code(*summary_groups: list[dict[str, Any]]) -> str | None:
    for summaries in summary_groups:
        for summary in summaries:
            failure = summary.get("failure")
            if isinstance(failure, dict) and isinstance(failure.get("code"), str):
                return failure["code"]
    return None


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _max_bucket(values: Any) -> str | None:
    buckets = [value for value in values if isinstance(value, str)]
    if not buckets:
        return None
    return max(buckets, key=lambda value: _BUCKET_RANK.get(value, 0))
