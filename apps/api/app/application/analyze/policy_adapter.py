from collections.abc import Iterable
from typing import Any, cast

from app.domain.policy import PolicyOrchestrator
from app.domain.types.common import ReasonCode
from app.domain.types.policy import (
    ContextRiskEvidence,
    PolicyAction,
    PolicyActionSettings,
    PolicyDecisionRequest,
    PolicyInputEvidence,
    PolicyMlEvidence,
    PolicyRuleEvidence,
    PolicySeverity,
    build_context_risk_evidence,
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
    filter_rules: Iterable[Any] | None = None,
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
    rules.extend(_context_label_policy_rules(classifier_outcome, filter_rules or []))
    return PolicyDecisionRequest(
        request_id=request_id,
        input_ids=[item.input_id for item in input_evidence],
        evidence_codes=list(evidence_codes or []),
        rules=rules,
        inputs=input_evidence,
        ml=_policy_ml_evidence(classifier_outcome),
        action_settings=action_settings or PolicyActionSettings(),
    )


def _context_label_policy_rules(classifier_outcome: Any, filter_rules: Iterable[Any]) -> list[PolicyRuleEvidence]:
    context = _context_risk_evidence(
        classifier_outcome,
        getattr(classifier_outcome, "failure", None),
        getattr(classifier_outcome, "verifier_summaries", []) or [],
    )
    if context.status not in {"verified", "candidate"} or not context.labels:
        return []
    rules_by_label = {
        str(getattr(rule, "detector_key", "")): rule
        for rule in filter_rules
        if getattr(rule, "origin", None) == "built_in"
        and getattr(rule, "category", None) == "Context Risk"
        and getattr(rule, "enabled", False)
        and getattr(rule, "archived_at", None) is None
    }
    evidence: list[PolicyRuleEvidence] = []
    for label in context.labels:
        rule = rules_by_label.get(label)
        if rule is None:
            continue
        action = _TO_CANONICAL.get(str(getattr(rule, "action", "WARN")), "warn")
        evidence.append(
            PolicyRuleEvidence(
                action="block" if action == "mask" else action,
                severity=_severity_from_rule(getattr(rule, "severity", "medium")),
                reason_code=context.reason_code,
                masking_supported=False,
            )
        )
    return evidence


def _severity_from_rule(value: Any) -> PolicySeverity:
    severity = str(value)
    if severity in {"info", "low", "medium", "high", "critical"}:
        return cast(PolicySeverity, severity)
    return "medium"


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
    context = _context_risk_evidence(classifier_outcome, failure, summaries)
    return PolicyMlEvidence(
        classifier_enabled=bool(getattr(classifier_outcome, "enabled", False)),
        classifier_has_candidates=bool(getattr(classifier_outcome, "has_candidates", False)) or context.candidate_count > 0,
        classifier_failed=failure is not None,
        verifier_failed=failure is not None and "VERIFIER" in str(getattr(failure, "code", "")).upper(),
        verifier_summary_present=bool(summaries),
        context=context,
    )


def _context_risk_evidence(
    classifier_outcome: Any,
    failure: Any,
    verifier_summaries: list[dict[str, Any]],
) -> ContextRiskEvidence:
    value = getattr(classifier_outcome, "context_risk", None)
    if isinstance(value, ContextRiskEvidence):
        return value
    if isinstance(value, dict):
        return ContextRiskEvidence.model_validate(value)
    failure_code = getattr(failure, "code", None) if failure is not None else None
    has_candidates = bool(getattr(classifier_outcome, "has_candidates", False))
    classification_summaries = [{"candidate_count": 1, "has_candidates": True}] if has_candidates else []
    return build_context_risk_evidence(
        enabled=bool(getattr(classifier_outcome, "enabled", False)),
        classification_summaries=classification_summaries,
        verifier_summaries=verifier_summaries,
        failure_code=failure_code if isinstance(failure_code, str) else None,
    )
