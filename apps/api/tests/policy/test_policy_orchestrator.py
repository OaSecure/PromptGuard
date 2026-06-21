import pytest

from app.domain.policy import PolicyOrchestrator
from app.domain.types.policy import (
    PolicyDecisionRequest,
    PolicyInputEvidence,
    PolicyMlEvidence,
    PolicyRuleEvidence,
)


def _request(*rules, scanned=True, ml=None):
    return PolicyDecisionRequest(
        request_id="req-policy-1",
        input_ids=["input-1"],
        inputs=[PolicyInputEvidence(input_id="input-1", content_scanned=scanned)],
        rules=list(rules),
        ml=ml or PolicyMlEvidence(),
    )


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
def test_unscanned_inputs_fail_closed(scan_case):
    decision = PolicyOrchestrator().decide(_request(scanned=False))
    assert scan_case
    assert decision.action == "block"
    assert decision.reason_code == "CONTENT_NOT_SCANNED"


def test_mask_is_preserved_only_when_origin_supports_masking():
    orchestrator = PolicyOrchestrator()
    assert orchestrator.decide(_request(_rule("mask", masking_supported=True))).action == "mask"
    assert orchestrator.decide(_request(_rule("mask", masking_supported=False))).action == "block"
    assert orchestrator.decide(
        _request(_rule("mask", masking_supported=True), _rule("mask", masking_supported=False))
    ).action == "block"


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


@pytest.mark.parametrize("failure", ["classifier_failed", "verifier_failed"])
def test_ml_failures_fail_closed(failure):
    ml = PolicyMlEvidence(**{failure: True})
    assert PolicyOrchestrator().decide(_request(ml=ml)).action == "block"


def test_verifier_summary_has_no_new_policy_meaning():
    ml = PolicyMlEvidence(verifier_summary_present=True)
    assert PolicyOrchestrator().decide(_request(ml=ml)).action == "allow"


def test_unmapped_rule_reason_remains_safe_and_deterministic():
    rule = PolicyRuleEvidence(action="block", severity="high")
    decision = PolicyOrchestrator().decide(_request(rule))
    assert decision.action == "block"
    assert decision.reason_code == "INTERNAL_POLICY_REASON_UNMAPPED"
