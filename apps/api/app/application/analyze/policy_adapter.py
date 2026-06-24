from collections.abc import Iterable
from typing import Any

from app.domain.policy import PolicyOrchestrator
from app.domain.types.common import ReasonCode
from app.domain.types.policy import (
    PolicyAction,
    PolicyActionSettings,
    PolicyDecisionRequest,
    PolicyInputEvidence,
    PolicyMlEvidence,
    PolicyRuleEvidence,
)
from app.ports.policy import PolicyOrchestratorPort

_TO_CANONICAL: dict[str, PolicyAction] = {
    "ALLOW": "allow",
    "WARN": "warn",
    "MASK": "mask",
    "BLOCK": "block",
}
_TO_LEGACY = {value: key for key, value in _TO_CANONICAL.items()}


def get_policy_orchestrator() -> PolicyOrchestratorPort:
    return PolicyOrchestrator()


def to_legacy_action(action: PolicyAction) -> str:
    return _TO_LEGACY[action]


def build_policy_request(
    request_id: str,
    inputs: Iterable[Any],
    matched_inputs: Iterable[tuple[int, Any, list[Any]]],
    classifier_outcome: Any,
    input_results: Iterable[Any] | None = None,
    evidence_codes: Iterable[ReasonCode] | None = None,
    action_settings: PolicyActionSettings | None = None,
) -> PolicyDecisionRequest:
    scanned_by_id = {str(item.input_id): bool(item.content_scanned) for item in input_results or []}
    input_evidence = []
    for item in inputs:
        input_id = str(item.input_id)
        input_evidence.append(
            PolicyInputEvidence(input_id=input_id, content_scanned=scanned_by_id.get(input_id, bool(item.content_included)))
        )
    rules: list[PolicyRuleEvidence] = []
    for _index, item, matches in matched_inputs:
        for match in matches:
            rules.append(
                PolicyRuleEvidence(
                    action=_TO_CANONICAL.get(str(match.action), "block"),
                    severity=match.severity,
                    reason_code=_safe_reason_code(match),
                    masking_supported=item.source == "composer",
                )
            )
    return PolicyDecisionRequest(
        request_id=request_id,
        input_ids=[item.input_id for item in input_evidence],
        evidence_codes=list(evidence_codes or []),
        rules=rules,
        inputs=input_evidence,
        ml=_policy_ml_evidence(classifier_outcome),
        action_settings=action_settings or PolicyActionSettings(),
    )


def _safe_reason_code(match: Any) -> ReasonCode:
    category = str(getattr(match, "category", "")).upper()
    if "PII" in category or "PAYMENT" in category:
        return "LEXICAL_HIGH_RISK_PII_SIGNAL"
    if "SECRET" in category or "CREDENTIAL" in category:
        return "LEXICAL_DETERMINISTIC_SECRET_SIGNAL"
    return "INTERNAL_POLICY_REASON_UNMAPPED"


def _policy_ml_evidence(classifier_outcome: Any) -> PolicyMlEvidence:
    failure = getattr(classifier_outcome, "failure", None)
    summaries = getattr(classifier_outcome, "verifier_summaries", []) or []
    return PolicyMlEvidence(
        classifier_enabled=bool(getattr(classifier_outcome, "enabled", False)),
        classifier_has_candidates=bool(getattr(classifier_outcome, "has_candidates", False)),
        classifier_failed=failure is not None,
        verifier_failed=failure is not None and "VERIFIER" in str(getattr(failure, "code", "")).upper(),
        verifier_summary_present=bool(summaries),
    )
