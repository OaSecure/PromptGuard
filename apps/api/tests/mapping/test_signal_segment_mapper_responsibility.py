import ast
from pathlib import Path

from app.mapping import SignalMappingPolicy, SignalMappingRequest, map_signals_to_segments


FORBIDDEN_IMPORT_PARTS = {
    "scanner",
    "normalizer",
    "embedding",
    "classifier",
    "verifier",
    "policy",
    "routes",
    "storage",
}


def test_mapping_package_source_does_not_import_forbidden_modules_with_ast():
    package_root = Path(__file__).parents[2] / "app" / "mapping"

    forbidden: list[str] = []
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    if _is_forbidden(module_name):
                        forbidden.append(f"{path.name}:{module_name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_name = node.module
                if _is_forbidden(module_name):
                    forbidden.append(f"{path.name}:{module_name}")

    assert forbidden == []


def test_signal_mapper_does_not_rescan_keywords(monkeypatch):
    calls: list[str] = []
    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if "scanner" in name or "detector" in name:
            calls.append(name)
            raise AssertionError(f"forbidden import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)

    result = map_signals_to_segments(
        SignalMappingRequest(
            input_id="input-1",
            segments=[],
            atoms=[],
            lexical_signals=[],
            mapping_policy=SignalMappingPolicy(),
        )
    )

    assert result.failure is None
    assert calls == []


def test_signal_mapper_does_not_create_classifier_policy_or_verifier_outputs():
    result = map_signals_to_segments(
        SignalMappingRequest(
            input_id="input-1",
            segments=[],
            atoms=[],
            lexical_signals=[],
            mapping_policy=SignalMappingPolicy(),
        )
    )

    dumped = str(result.model_dump())

    assert "label" not in dumped
    assert "label_scores" not in dumped
    assert "verification" not in dumped
    assert "policy" not in dumped
    assert "action" not in dumped


def _is_forbidden(module_name: str) -> bool:
    parts = set(module_name.split("."))
    return bool(parts & FORBIDDEN_IMPORT_PARTS)
