from app.domain.types.common import ReasonCode
from app.domain.types.policy import (
    PolicyAction,
    PolicyDecision,
    PolicyDecisionRequest,
    PolicyRuleEvidence,
    PolicySeverity,
)

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
        if not request.inputs:
            return _configured_decision(request.action_settings.empty_input_action, "EMPTY_INPUT")
        context_decision = _context_risk_decision(request)
        if context_decision is not None:
            return context_decision
        return PolicyDecision(action="allow", reason_code="NO_RISK_DETECTED", severity="info")

    def _decision_for_rule(self, selected: PolicyRuleEvidence, request: PolicyDecisionRequest) -> PolicyDecision:
        mask_unsupported = any(
            rule.action == "mask" and not rule.masking_supported for rule in request.rules
        )
        if selected.action == "mask" and mask_unsupported:
            return _configured_decision(
                request.action_settings.unsupported_mask_fallback_action,
                selected.reason_code,
            )
        if selected.action == "allow":
            context_decision = _context_risk_decision(request)
            if context_decision is not None:
                return context_decision
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
            rules.append(_configured_rule(request.action_settings.parser_or_ocr_failure_action, "PARSER_OR_OCR_FAILED"))
        if any(not item.content_scanned for item in request.inputs) or _has_content_not_scanned_code(request):
            rules.append(_configured_rule(request.action_settings.content_not_scanned_action, "CONTENT_NOT_SCANNED"))
        return rules


def _has_content_not_scanned_code(request: PolicyDecisionRequest) -> bool:
    return any(code in request.evidence_codes for code in ("CONTENT_NOT_SCANNED", "UNSUPPORTED_FILE"))


def _configured_rule(action: PolicyAction, reason_code: ReasonCode) -> PolicyRuleEvidence:
    return PolicyRuleEvidence(
        action=action,
        severity=_severity_for_action(action),
        reason_code=reason_code,
        masking_supported=False,
    )


def _configured_decision(action: PolicyAction, reason_code: ReasonCode) -> PolicyDecision:
    return PolicyDecision(action=action, reason_code=reason_code, severity=_severity_for_action(action))


def _context_risk_decision(request: PolicyDecisionRequest) -> PolicyDecision | None:
    if not request.ml.classifier_enabled:
        return None
    context = request.ml.context
    if context.status in {"verified", "candidate"}:
        return _configured_decision(request.action_settings.context_classifier_action, context.reason_code)
    if context.status in {"timeout", "failed"} and (context.candidate_count > 0 or context.accepted_count > 0):
        return _configured_decision(request.action_settings.context_classifier_action, context.reason_code)
    if request.ml.classifier_has_candidates:
        return _configured_decision(request.action_settings.context_classifier_action, "RISK_CONTEXT_LR_ONLY")
    return None


def _severity_for_action(action: PolicyAction) -> PolicySeverity:
    if action == "block":
        return "high"
    if action == "warn":
        return "medium"
    return "info"
