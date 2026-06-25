import pytest
from types import SimpleNamespace

from app.application.analyze.policy_adapter import build_policy_request
from app.domain.policy import PolicyOrchestrator
from app.domain.types.policy import (
    ContextRiskEvidence,
    PolicyActionSettings,
    PolicyDecisionRequest,
    PolicyInputEvidence,
    PolicyMlEvidence,
    PolicyRuleEvidence,
)


def _request(*rules, scanned=True, ml=None, evidence_codes=None):
    return PolicyDecisionRequest(
        request_id="req-policy-1",
        input_ids=["input-1"],
        evidence_codes=list(evidence_codes or []),
        inputs=[PolicyInputEvidence(input_id="input-1", content_scanned=scanned)],
        rules=list(rules),
        ml=ml or PolicyMlEvidence(),
    )


def _request_with_settings(settings: PolicyActionSettings, *rules, scanned=True, ml=None, evidence_codes=None):
    request = _request(*rules, scanned=scanned, ml=ml, evidence_codes=evidence_codes)
    request.action_settings = settings
    return request


def _rule(action, *, masking_supported=True, severity="medium"):
    return PolicyRuleEvidence(
        action=action,
        severity=severity,
        reason_code="LEXICAL_HIGH_RISK_PII_SIGNAL",
        masking_supported=masking_supported,
    )


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ([], "allow"),
        (["allow"], "allow"),
        (["warn"], "warn"),
        (["mask"], "mask"),
        (["block"], "block"),
        (["warn", "mask"], "mask"),
        (["warn", "block"], "block"),
        (["mask", "block"], "block"),
        (["warn", "mask", "block"], "block"),
    ],
)
def test_policy_action_priority_matrix(actions, expected):
    decision = PolicyOrchestrator().decide(_request(*[_rule(action) for action in actions]))
    assert decision.action == expected


@pytest.mark.parametrize("scan_case", ["unavailable", "content_not_scanned", "file_reference"])
def test_unscanned_inputs_warn_with_content_not_scanned_notice(scan_case):
    decision = PolicyOrchestrator().decide(_request(scanned=False, evidence_codes=["CONTENT_NOT_SCANNED"]))
    assert scan_case
    assert decision.action == "warn"
    assert decision.reason_code == "CONTENT_NOT_SCANNED"


def test_parser_or_ocr_failure_warns_without_becoming_allow_or_block():
    decision = PolicyOrchestrator().decide(_request(scanned=False, evidence_codes=["PARSER_OR_OCR_FAILED"]))
    assert decision.action == "warn"
    assert decision.reason_code == "PARSER_OR_OCR_FAILED"


def test_content_not_scanned_and_parser_failure_use_configured_notice_actions():
    settings = PolicyActionSettings(content_not_scanned_action="block", parser_or_ocr_failure_action="warn")

    content_not_scanned = PolicyOrchestrator().decide(
        _request_with_settings(settings, scanned=False, evidence_codes=["CONTENT_NOT_SCANNED"])
    )
    parser_failed = PolicyOrchestrator().decide(_request_with_settings(settings, evidence_codes=["PARSER_OR_OCR_FAILED"]))

    assert content_not_scanned.action == "block"
    assert content_not_scanned.reason_code == "CONTENT_NOT_SCANNED"
    assert parser_failed.action == "warn"
    assert parser_failed.reason_code == "PARSER_OR_OCR_FAILED"


def test_mask_is_preserved_only_when_origin_supports_masking():
    orchestrator = PolicyOrchestrator()
    assert orchestrator.decide(_request(_rule("mask", masking_supported=True))).action == "mask"
    assert orchestrator.decide(_request(_rule("mask", masking_supported=False))).action == "block"
    assert orchestrator.decide(
        _request(_rule("mask", masking_supported=True), _rule("mask", masking_supported=False))
    ).action == "block"


def test_unsupported_mask_fallback_uses_configured_warn_or_block_only():
    settings = PolicyActionSettings(unsupported_mask_fallback_action="warn")

    decision = PolicyOrchestrator().decide(_request_with_settings(settings, _rule("mask", masking_supported=False)))

    assert decision.action == "warn"


@pytest.mark.parametrize("existing", ["warn", "mask", "block"])
def test_classifier_candidate_never_downgrades_existing_action(existing):
    ml = PolicyMlEvidence(classifier_enabled=True, classifier_has_candidates=True)
    assert PolicyOrchestrator().decide(_request(_rule(existing), ml=ml)).action == existing


def test_classifier_candidate_upgrades_allow_to_warn_but_disabled_classifier_does_not():
    orchestrator = PolicyOrchestrator()
    enabled = PolicyMlEvidence(classifier_enabled=True, classifier_has_candidates=True)
    disabled = PolicyMlEvidence(classifier_enabled=False, classifier_has_candidates=True)
    assert orchestrator.decide(_request(ml=enabled)).action == "warn"
    assert orchestrator.decide(_request(ml=disabled)).action == "allow"


def test_classifier_candidate_uses_configured_context_action_without_mask_target():
    ml = PolicyMlEvidence(classifier_enabled=True, classifier_has_candidates=True)
    settings = PolicyActionSettings(context_classifier_action="block")

    decision = PolicyOrchestrator().decide(_request_with_settings(settings, ml=ml))

    assert decision.action == "block"
    assert decision.reason_code == "RISK_CONTEXT_LR_ONLY"


def test_verified_context_evidence_uses_verifier_confirmed_reason():
    ml = PolicyMlEvidence(
        classifier_enabled=True,
        classifier_has_candidates=True,
        verifier_summary_present=True,
        context=ContextRiskEvidence(
            enabled=True,
            status="verified",
            candidate_count=1,
            accepted_count=1,
            labels=["INTERNAL_OPERATION_CONTEXT"],
            reason_code="RISK_CONTEXT_VERIFIER_CONFIRMED",
        ),
    )

    decision = PolicyOrchestrator().decide(_request(ml=ml))

    assert decision.action == "warn"
    assert decision.reason_code == "RISK_CONTEXT_VERIFIER_CONFIRMED"


def test_confirmed_context_label_uses_matching_filter_rule_action():
    classifier_outcome = SimpleNamespace(
        enabled=True,
        has_candidates=True,
        failure=None,
        verifier_summaries=[],
        context_risk=ContextRiskEvidence(
            enabled=True,
            status="verified",
            candidate_count=1,
            accepted_count=1,
            labels=["CONFIDENTIAL_BUSINESS_CONTEXT"],
            reason_code="RISK_CONTEXT_VERIFIER_CONFIRMED",
        ),
    )
    label_rule = SimpleNamespace(
        origin="built_in",
        category="Context Risk",
        detector_key="CONFIDENTIAL_BUSINESS_CONTEXT",
        enabled=True,
        archived_at=None,
        action="BLOCK",
        severity="critical",
    )

    request = build_policy_request(
        "req-context-label",
        [SimpleNamespace(input_id="input-1", content_included=True)],
        [],
        classifier_outcome,
        input_results=[SimpleNamespace(input_id="input-1", content_scanned=True)],
        filter_rules=[label_rule],
    )
    decision = PolicyOrchestrator().decide(request)

    assert decision.action == "block"
    assert decision.severity == "critical"
    assert decision.reason_code == "RISK_CONTEXT_VERIFIER_CONFIRMED"


def test_empty_input_uses_configured_empty_input_action():
    settings = PolicyActionSettings(empty_input_action="warn")

    decision = PolicyOrchestrator().decide(
        PolicyDecisionRequest(
            request_id="req-empty-policy",
            input_ids=[],
            inputs=[],
            action_settings=settings,
        )
    )

    assert decision.action == "warn"
    assert decision.reason_code == "EMPTY_INPUT"


@pytest.mark.parametrize("failure", ["classifier_failed", "verifier_failed"])
def test_ml_failures_without_candidates_do_not_create_context_policy_decisions(failure):
    ml = PolicyMlEvidence(
        classifier_enabled=True,
        **{failure: True},
        context=ContextRiskEvidence(
            enabled=True,
            status="failed",
            failure_code="VERIFIER_MODEL_FAILED" if failure == "verifier_failed" else "ANALYZE_CLASSIFIER_FAILED",
            reason_code="RISK_CONTEXT_LR_ONLY_VERIFIER_FAILED",
        ),
    )
    decision = PolicyOrchestrator().decide(_request(ml=ml))
    assert decision.action == "allow"
    assert decision.reason_code == "NO_RISK_DETECTED"


def test_verifier_failure_keeps_lr_candidate_warn_path():
    ml = PolicyMlEvidence(classifier_enabled=True, classifier_has_candidates=True, verifier_failed=True)
    decision = PolicyOrchestrator().decide(_request(ml=ml))
    assert decision.action == "warn"
    assert decision.reason_code == "RISK_CONTEXT_LR_ONLY"


def test_verifier_summary_has_no_new_policy_meaning():
    ml = PolicyMlEvidence(verifier_summary_present=True)
    assert PolicyOrchestrator().decide(_request(ml=ml)).action == "allow"


def test_context_timeout_uses_timeout_reason():
    ml = PolicyMlEvidence(
        classifier_enabled=True,
        context=ContextRiskEvidence(
            enabled=True,
            status="timeout",
            candidate_count=1,
            failure_code="ML_INFERENCE_TIMEOUT",
            reason_code="RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT",
        ),
    )
    decision = PolicyOrchestrator().decide(_request(ml=ml))
    assert decision.action == "warn"
    assert decision.reason_code == "RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT"


def test_context_timeout_without_candidates_does_not_create_context_policy_decision():
    ml = PolicyMlEvidence(
        classifier_enabled=True,
        context=ContextRiskEvidence(
            enabled=True,
            status="timeout",
            failure_code="ML_INFERENCE_TIMEOUT",
            reason_code="RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT",
        ),
    )
    decision = PolicyOrchestrator().decide(_request(ml=ml))
    assert decision.action == "allow"
    assert decision.reason_code == "NO_RISK_DETECTED"


def test_unmapped_rule_reason_remains_safe_and_deterministic():
    rule = PolicyRuleEvidence(action="block", severity="high")
    decision = PolicyOrchestrator().decide(_request(rule))
    assert decision.action == "block"
    assert decision.reason_code == "INTERNAL_POLICY_REASON_UNMAPPED"
