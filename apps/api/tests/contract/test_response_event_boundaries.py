import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

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


def test_dashboard_event_detail_projects_context_risk_evidence_separately():
    from app.routes.events import detail_item

    event = SimpleNamespace(
        id=UUID("10000000-0000-4000-8000-000000000001"),
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
        login_id="user-1",
        service="chatgpt",
        platform="chrome",
        action="WARN",
        risk_score=40,
        risk_level="medium",
        context_risk_evidence={
            "enabled": True,
            "status": "candidate",
            "candidate_count": 1,
            "accepted_count": 0,
            "labels": ["INTERNAL_OPERATION_CONTEXT"],
            "status_counts": {"uncertain": 1},
            "reason_code": "RISK_CONTEXT_LR_ONLY",
            "classifier_model_versions": [],
            "verifier_model_versions": [],
        },
    )
    user = SimpleNamespace(login_id="user-1", display_name="User One", username="user-one")
    event_input = SimpleNamespace(
        input_id="input-1",
        input_index=0,
        kind="text",
        source="composer",
        content_included=True,
        content_scanned=True,
        decision_basis="context_risk",
        content_unavailable_reason=None,
        limit_exceeded=None,
    )

    detail = detail_item(event, user, [], [event_input])

    assert detail.business_context_matches == []
    assert detail.detection_count == 0
    assert detail.context_risk_evidence is not None
    assert detail.context_risk_evidence.status == "candidate"
    assert detail.context_risk_evidence.labels == ["INTERNAL_OPERATION_CONTEXT"]
    assert detail.input_results[0].decision_basis == "context_risk"
