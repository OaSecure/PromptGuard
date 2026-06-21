import ast
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2] / "app"


def test_response_adapter_has_no_database_dependencies():
    path = API_ROOT / "interfaces" / "http" / "response_adapter.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(name.startswith(("sqlalchemy", "app.models", "app.events")) for name in imports)


def test_analyze_route_does_not_own_response_or_event_orm_serialization():
    source = (API_ROOT / "routes" / "analyze.py").read_text(encoding="utf-8")
    for forbidden in ("AnalysisEvent(", "EventInput(", "EventDetection(", "IdempotencyKey(", "return AnalyzeResponse("):
        assert forbidden not in source
    assert "build_analyze_response(" in source
    assert "serialize_event_write(" in source
