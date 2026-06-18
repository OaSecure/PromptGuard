import json
import hashlib
from uuid import UUID

from app.models.filters import FilterRule
from app.scanner.models import LexicalSignal
from app.services.filter_rules import evaluate_filter_rules


def _rule(kind: str, **values) -> FilterRule:
    defaults = dict(
        id=UUID("11111111-1111-4111-8111-111111111111"), origin="custom", kind=kind,
        category="Custom", label="Legacy", severity="high", action="MASK",
        enabled=True, editable_fields={}, version=1,
    )
    defaults.update(values)
    return FilterRule(**defaults)


SAFE_GROUP_ID = f"group:{hashlib.sha256(b'contract').hexdigest()[:12]}"


def test_legacy_keyword_and_regex_rules_are_evaluated_through_lexical_signals(monkeypatch):
    seen: list[LexicalSignal] = []
    from app.services import filter_rules

    real = filter_rules.scan_lexical_signals

    def capture(request):
        result = real(request)
        seen.extend(result.signals)
        return result

    monkeypatch.setattr(filter_rules, "scan_lexical_signals", capture)
    matches = evaluate_filter_rules(
        "Project---Hermes ticket ABC-1234",
        [_rule("keyword", keyword="Project-Hermes", placeholder="PROJECT"),
         _rule("regex", pattern=r"ABC-\d{4}", placeholder="TICKET",
               id=UUID("22222222-2222-4222-8222-222222222222"))],
    )
    assert {match.source for match in matches} == {"custom_keyword", "custom_regex"}
    assert {signal.match_basis for signal in seen} == {"keyword", "regex"}


def test_context_evidence_contains_only_safe_group_and_pattern_ids():
    secret_a, secret_b = "NDA-super-secret", "penalty-raw-secret"
    rule = _rule(
        "context_rule", placeholder="BUSINESS_CONTEXT", action="WARN", severity="medium",
        config_json={"keyword_groups": {"contract": [secret_a, secret_b]}, "min_condition_count": 2},
    )
    match = evaluate_filter_rules(f"{secret_a} and {secret_b}", [rule])[0]
    encoded = json.dumps(match.safe_evidence)
    assert match.safe_evidence["matched_condition_count"] == 2
    assert match.safe_evidence["matched_group_ids"] == [SAFE_GROUP_ID]
    assert match.safe_evidence["matched_pattern_ids"] == [
        f"rule:{rule.id}:{SAFE_GROUP_ID}:pattern:0",
        f"rule:{rule.id}:{SAFE_GROUP_ID}:pattern:1",
    ]
    assert secret_a not in encoded and secret_b not in encoded
    assert "matched_keywords" not in match.safe_evidence
    assert "contract" not in encoded


def test_scanner_contract_has_no_policy_fields_or_raw_rule_material():
    forbidden = {"action", "recommended_action", "reason_code", "user_notice", "user_message"}
    assert forbidden.isdisjoint(LexicalSignal.model_fields)
    rule = _rule("regex", pattern=r"RAW-SECRET-\d+", placeholder="SECRET")
    match = evaluate_filter_rules("RAW-SECRET-42", [rule])[0]
    encoded = repr(match.safe_evidence)
    assert "RAW-SECRET" not in encoded
    assert "\\d+" not in encoded
