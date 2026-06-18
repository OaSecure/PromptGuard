from app.atoms.models import ParsedBlock, ParsedDocument, TextRange
from app.normalization import NormalizerRequest, normalize_document
from app.scanner import LexicalRule, LexicalScanRequest, scan_lexical_signals


def _normalized(text: str):
    document = ParsedDocument(input_id="input-1", blocks=[ParsedBlock(block_id="block-1", input_id="input-1", text=text)])
    return normalize_document(NormalizerRequest(document=document))


def test_scanner_uses_normalized_text_and_restores_original_range():
    result = scan_lexical_signals(
        LexicalScanRequest(
            normalized_document=_normalized("Project---Hermes"),
            rules=[LexicalRule(pattern_id="project", kind="keyword", expression="Project-Hermes", signal_type="CUSTOM_KEYWORD")],
        )
    )

    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.normalized_range == TextRange(start=0, end=14)
    assert signal.original_range == TextRange(start=0, end=16)
    assert signal.match_basis == "keyword"
    assert signal.deterministic is True


def test_scanner_supports_minimal_regex_rules_without_returning_match_value():
    result = scan_lexical_signals(
        LexicalScanRequest(
            normalized_document=_normalized("ticket ABC-1234"),
            rules=[LexicalRule(pattern_id="ticket-id", kind="regex", expression=r"ABC-\d{4}", signal_type="CUSTOM_REGEX")],
        )
    )

    assert len(result.signals) == 1
    payload = result.signals[0].model_dump()
    assert payload["pattern_id"] == "ticket-id"
    assert payload["match_basis"] == "regex"
    assert "ABC-1234" not in repr(payload)


def test_scanner_result_schema_forbids_policy_and_raw_value_fields():
    result = scan_lexical_signals(
        LexicalScanRequest(
            normalized_document=_normalized("secret-marker"),
            rules=[LexicalRule(pattern_id="marker", kind="keyword", expression="secret-marker", signal_type="MARKER")],
        )
    )

    forbidden = {"raw_value", "matched_value", "value", "action", "reason_code", "user_message", "confidence_hint"}
    assert forbidden.isdisjoint(type(result.signals[0]).model_fields)
    assert "secret-marker" not in repr(result.model_dump())


def test_invalid_regex_is_isolated_as_warning():
    result = scan_lexical_signals(
        LexicalScanRequest(
            normalized_document=_normalized("safe"),
            rules=[LexicalRule(pattern_id="invalid", kind="regex", expression="[", signal_type="CUSTOM_REGEX")],
        )
    )

    assert result.signals == []
    assert result.warnings == ["INVALID_REGEX:invalid"]


def test_mapping_failure_discards_signal_without_raw_content():
    document = _normalized("secret-marker")
    document.blocks[0].offset_map = []

    result = scan_lexical_signals(
        LexicalScanRequest(
            normalized_document=document,
            rules=[LexicalRule(pattern_id="rule-marker-1", kind="keyword", expression="secret-marker", signal_type="MARKER")],
        )
    )

    assert result.signals == []
    assert result.failures[0].code == "OFFSET_MAPPING_FAILED"
    assert "secret-marker" not in repr(result.model_dump())
