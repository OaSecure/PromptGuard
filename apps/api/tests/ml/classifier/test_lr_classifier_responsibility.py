import ast
from pathlib import Path


def test_classifier_package_does_not_import_forbidden_pipeline_modules():
    package_root = Path(__file__).resolve().parents[3] / "app" / "ml" / "classifier"
    forbidden = {
        "routes",
        "policy",
        "verifier",
        "events",
        "parser",
        "scanner",
        "mapper",
        "normalizer",
        "normalization",
    }

    for path in package_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any(any(part == forbidden_name for part in name.split(".")) for name in imports for forbidden_name in forbidden)
