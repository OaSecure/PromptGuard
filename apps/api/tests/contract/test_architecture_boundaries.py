import ast
from pathlib import Path

API_ROOT = Path(__file__).parents[2]
APP_ROOT = API_ROOT / "app"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: names.add(node.module)
    return names


def test_domain_and_ports_do_not_import_delivery_or_concrete_infrastructure():
    forbidden = ("fastapi", "sqlalchemy", "app.routes", "app.models", "app.db", "app.infrastructure", "app.runtime", "app.services")
    for package in (APP_ROOT / "domain" / "types", APP_ROOT / "ports"):
        for path in package.glob("*.py"):
            violations = {name for name in imports(path) if name.startswith(forbidden)}
            assert not violations, f"{path}: {sorted(violations)}"


def test_input_envelope_is_not_imported_outside_analyze_application():
    allowed = APP_ROOT / "application" / "analyze"
    violations = []
    for path in APP_ROOT.rglob("*.py"):
        if allowed in path.parents: continue
        if "app.application.analyze.input_envelope" in imports(path): violations.append(path)
    assert not violations
