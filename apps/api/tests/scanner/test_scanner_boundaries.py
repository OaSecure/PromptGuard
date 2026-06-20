import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.atoms.models import TextRange
from app.scanner.models import LexicalSignal


def test_scanner_signal_has_no_policy_or_raw_value_fields():
    forbidden = {"raw_value", "matched_value", "value", "action", "reason_code", "user_message", "confidence_hint"}
    assert forbidden.isdisjoint(LexicalSignal.model_fields)
    assert LexicalSignal.model_fields["severity_hint"].default is None
    assert LexicalSignal.model_fields["value_fingerprint"].default is None


def test_new_modules_do_not_import_analyze_policy_or_storage_layers():
    root = Path(__file__).parents[2] / "app"
    forbidden_prefixes = ("app.routes", "app.models.events", "app.services.filter_rules", "app.segmenter", "app.ml")
    for relative in ("normalization/normalizer.py", "scanner/scanner.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
        assert not any(name.startswith(forbidden_prefixes) for name in imports)


@pytest.mark.parametrize("metadata_key", ["raw_value", "matched_value", "action", "reason_code", "user_message"])
def test_scanner_signal_metadata_rejects_raw_or_policy_keys(metadata_key):
    with pytest.raises(ValidationError):
        LexicalSignal(
            signal_id="sig_contract",
            input_id="input-1",
            block_id="block-1",
            signal_type="CUSTOM_KEYWORD",
            pattern_id="pattern-1",
            match_basis="keyword",
            normalized_range=TextRange(start=0, end=4),
            original_range=TextRange(start=0, end=4),
            metadata={metadata_key: "forbidden"},
        )
