import ast
from pathlib import Path

from app.domain.types.policy import PolicyDecision, PolicyDecisionRequest

API_ROOT = Path(__file__).resolve().parents[2] / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_policy_domain_has_no_framework_or_runtime_dependencies():
    forbidden = ("fastapi", "sqlalchemy", "app.routes", "app.models", "app.ml", "app.parser", "app.scanner")
    for path in (API_ROOT / "domain" / "policy").glob("*.py"):
        assert not any(name.startswith(forbidden) for name in _imports(path))


def test_only_policy_decides_action():
    route_source = (API_ROOT / "routes" / "analyze.py").read_text(encoding="utf-8")
    assert "final_action_for_" not in route_source
    assert "action_for_matches(" not in route_source
    assert "policy_orchestrator.decide(policy_request)" in route_source

    for package in ("parser", "scanner", "ml"):
        for path in (API_ROOT / package).rglob("*.py"):
            assert "PolicyDecision(" not in path.read_text(encoding="utf-8")


def test_policy_contract_rejects_raw_runtime_fields():
    forbidden = {"raw_text", "prompt", "file_ref", "filename", "embedding", "logits", "exact_score"}
    assert forbidden.isdisjoint(PolicyDecisionRequest.model_fields)
    assert forbidden.isdisjoint(PolicyDecision.model_fields)
