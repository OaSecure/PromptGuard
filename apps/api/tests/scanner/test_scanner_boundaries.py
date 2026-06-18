import ast
from pathlib import Path

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
