from app.domain.types.common import ReasonCode
from app.domain.types.policy import PolicyDecision, PolicyDecisionRequest, PolicyRuleEvidence

_ACTION_PRIORITY = {"allow": 0, "warn": 1, "mask": 2, "block": 3}
_SEVERITY_PRIORITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class PolicyOrchestrator:
    """Deterministically selects a final action from privacy-safe evidence."""

    def decide(self, request: PolicyDecisionRequest) -> PolicyDecision:
        selected = self._selected_rule(request)
        if selected is None:
            return self._ml_or_allow_decision(request)
        return self._decision_for_rule(selected, request)

    def _selected_rule(self, request: PolicyDecisionRequest) -> PolicyRuleEvidence | None:
        return self._highest_priority_rule([*request.rules, *self._policy_failure_rules(request)])

    def _ml_or_allow_decision(self, request: PolicyDecisionRequest) -> PolicyDecision:
        if request.ml.classifier_enabled and request.ml.classifier_has_candidates:
            return PolicyDecision(action="warn", reason_code="RISK_CONTEXT_LR_ONLY", severity="medium")
        return PolicyDecision(action="allow", reason_code="NO_RISK_DETECTED", severity="info")

    def _decision_for_rule(self, selected: PolicyRuleEvidence, request: PolicyDecisionRequest) -> PolicyDecision:
        mask_unsupported = any(
            rule.action == "mask" and not rule.masking_supported for rule in request.rules
        )
        if selected.action == "mask" and mask_unsupported:
            return PolicyDecision(action="block", reason_code=selected.reason_code, severity="high")
        if selected.action == "allow" and request.ml.classifier_enabled and request.ml.classifier_has_candidates:
            return PolicyDecision(action="warn", reason_code="RISK_CONTEXT_LR_ONLY", severity="medium")
        return PolicyDecision(action=selected.action, reason_code=selected.reason_code, severity=selected.severity)

    @staticmethod
    def _highest_priority_rule(rules: list[PolicyRuleEvidence]) -> PolicyRuleEvidence | None:
        if not rules:
            return None
        return max(
            rules,
            key=lambda item: (_ACTION_PRIORITY[item.action], _SEVERITY_PRIORITY[item.severity]),
        )

    @staticmethod
    def _policy_failure_rules(request: PolicyDecisionRequest) -> list[PolicyRuleEvidence]:
        rules: list[PolicyRuleEvidence] = []
        if "PARSER_OR_OCR_FAILED" in request.evidence_codes:
            rules.append(_warn_rule("PARSER_OR_OCR_FAILED"))
        if any(not item.content_scanned for item in request.inputs) or _has_content_not_scanned_code(request):
            rules.append(_warn_rule("CONTENT_NOT_SCANNED"))
        return rules


def _has_content_not_scanned_code(request: PolicyDecisionRequest) -> bool:
    return any(code in request.evidence_codes for code in ("CONTENT_NOT_SCANNED", "UNSUPPORTED_FILE"))


def _warn_rule(reason_code: ReasonCode) -> PolicyRuleEvidence:
    return PolicyRuleEvidence(
        action="warn",
        severity="medium",
        reason_code=reason_code,
        masking_supported=False,
    )
