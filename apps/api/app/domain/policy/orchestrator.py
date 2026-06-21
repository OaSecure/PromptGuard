from app.domain.types.policy import PolicyDecision, PolicyDecisionRequest, PolicyRuleEvidence

_ACTION_PRIORITY = {"allow": 0, "warn": 1, "mask": 2, "block": 3}
_SEVERITY_PRIORITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class PolicyOrchestrator:
    """Deterministically selects a final action from privacy-safe evidence."""

    def decide(self, request: PolicyDecisionRequest) -> PolicyDecision:
        if any(not item.content_scanned for item in request.inputs):
            return PolicyDecision(action="block", reason_code="CONTENT_NOT_SCANNED", severity="high")

        if request.ml.classifier_failed or request.ml.verifier_failed:
            return PolicyDecision(
                action="block",
                reason_code="INTERNAL_POLICY_REASON_UNMAPPED",
                severity="high",
            )

        selected = self._highest_priority_rule(request.rules)
        if selected is None:
            if request.ml.classifier_enabled and request.ml.classifier_has_candidates:
                return PolicyDecision(action="warn", reason_code="RISK_CONTEXT_LR_ONLY", severity="medium")
            return PolicyDecision(action="allow", reason_code="NO_RISK_DETECTED", severity="info")

        if selected.action == "mask" and any(
            rule.action == "mask" and not rule.masking_supported for rule in request.rules
        ):
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
