import json
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.events import AnalysisEvent, EventDetection, EventInput
from app.routes import dashboard_overview


class _ScalarResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _ExecuteResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return _ScalarResult(self.items)


class _RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, *, events=None, detections=None, event_inputs=None, users=None):
        self.events = list(events or [])
        self.detections = list(detections or [])
        self.event_inputs = list(event_inputs or [])
        self.users = list(users or [])
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "FROM analysis_events JOIN users" in statement_text:
            login_ids_by_user_id = {user.id: user.login_id for user in self.users}
            return _RowsResult(
                [
                    (event, login_ids_by_user_id[event.user_id])
                    for event in self.events
                    if event.user_id in login_ids_by_user_id
                ]
            )
        if "FROM analysis_events" in statement_text:
            return _ExecuteResult(self.events)
        if "FROM event_detections" in statement_text:
            return _ExecuteResult(self.detections)
        if "FROM event_inputs" in statement_text:
            return _ExecuteResult(self.event_inputs)
        return _ExecuteResult([])


def _event(
    *,
    user_id: uuid.UUID | None = None,
    action: str,
    risk_level: str,
    risk_score: int,
    created_at: datetime,
    service: str | None = "ChatGPT",
) -> AnalysisEvent:
    return AnalysisEvent(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        prompt_hash="abcdef1234567890abcdef1234567890",
        prompt_hash_key_id="dev-key-1",
        action=action,
        risk_score=risk_score,
        risk_level=risk_level,
        filter_rule_set_version="built-in:2026-05-30",
        service=service,
        service_domain="chat.openai.com",
        platform="web",
        created_at=created_at,
    )


def _user(*, user_id: uuid.UUID, login_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, login_id=login_id)


def _detection(event: AnalysisEvent, *, count: int = 1) -> EventDetection:
    return EventDetection(
        id=uuid.uuid4(),
        event_id=event.id,
        category="PII",
        type="EMAIL",
        source="built_in_detector",
        severity="medium",
        confidence=100,
        count=count,
        reason_code="PII_EMAIL_DETECTED",
        match_count=count,
        safe_evidence={"value_lengths": [16] * count},
    )


def _event_input(
    event: AnalysisEvent,
    *,
    input_index: int,
    content_included: bool,
    decision_basis: str,
    reason: str | None = None,
) -> EventInput:
    return EventInput(
        id=uuid.uuid4(),
        event_id=event.id,
        input_id=f"input-{input_index}",
        input_index=input_index,
        kind="text",
        source="composer",
        size_bucket="empty",
        content_included=content_included,
        content_scanned=content_included,
        decision_basis=decision_basis,
        content_unavailable_reason=reason,
    )


def _client(fake_session: _FakeSession, *, role: str | None = "ADMIN") -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_overview.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid dashboard session")
        if role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return SimpleNamespace(id=uuid.uuid4(), role=role, status="ACTIVE")

    app.dependency_overrides[dashboard_overview.get_db_session] = override_session
    app.dependency_overrides[dashboard_overview.require_dashboard_admin_session] = override_admin
    return TestClient(app)


def test_dashboard_overview_requires_dashboard_admin_session() -> None:
    fake_session = _FakeSession()

    assert _client(fake_session, role=None).get("/dashboard/overview").status_code == 401
    assert _client(fake_session, role="USER").get("/dashboard/overview").status_code == 403
    assert _client(fake_session, role="ADMIN").get("/dashboard/overview").status_code == 200


def test_dashboard_overview_returns_empty_summary(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_overview, "utc_today", lambda: date(2026, 5, 30))

    response = _client(_FakeSession()).get("/dashboard/overview")
    body = response.json()

    assert response.status_code == 200
    expected_fields = {
        "period_start",
        "period_end",
        "event_count",
        "blocked_count",
        "masked_count",
        "warned_count",
        "allowed_count",
        "active_user_count",
        "content_unavailable_event_count",
        "last_event_at",
        "action_counts",
        "risk_level_counts",
        "detector_category_counts",
        "period_buckets",
    }
    removed_fields = {"total_events", "active_users", "period_event_counts", "recent_events"}
    assert expected_fields.issubset(body)
    assert not removed_fields.intersection(body)
    assert body["period_start"] == "2026-05-01T00:00:00Z"
    assert body["period_end"].startswith("2026-05-30T23:59:59")
    assert body["event_count"] == 0
    assert body["blocked_count"] == 0
    assert body["masked_count"] == 0
    assert body["warned_count"] == 0
    assert body["allowed_count"] == 0
    assert body["active_user_count"] == 0
    assert body["content_unavailable_event_count"] == 0
    assert body["last_event_at"] is None
    assert body["action_counts"] == [
        {"action": "allow", "count": 0},
        {"action": "warn", "count": 0},
        {"action": "mask", "count": 0},
        {"action": "block", "count": 0},
    ]
    assert body["risk_level_counts"] == [
        {"risk_level": "low", "count": 0},
        {"risk_level": "medium", "count": 0},
        {"risk_level": "high", "count": 0},
        {"risk_level": "critical", "count": 0},
    ]
    assert body["detector_category_counts"] == []
    assert isinstance(body["period_buckets"], list)
    assert len(body["period_buckets"]) == 30
    assert {"bucket_start", "bucket_end", "event_count", "blocked_count", "masked_count", "warned_count"}.issubset(
        body["period_buckets"][0]
    )
    assert body["period_buckets"][0]["event_count"] == 0
    assert body["period_buckets"][0]["blocked_count"] == 0
    assert body["period_buckets"][0]["masked_count"] == 0
    assert body["period_buckets"][0]["warned_count"] == 0


def test_dashboard_overview_aggregates_30_day_summary(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_overview, "utc_today", lambda: date(2026, 5, 30))
    user_a = uuid.uuid4()
    user_a_alias = uuid.uuid4()
    user_b = uuid.uuid4()
    masked = _event(
        user_id=user_a,
        action="MASK",
        risk_level="medium",
        risk_score=55,
        created_at=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
    )
    blocked = _event(
        user_id=user_a_alias,
        action="BLOCK",
        risk_level="critical",
        risk_score=95,
        created_at=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
    )
    warned = _event(
        user_id=user_b,
        action="WARN",
        risk_level="high",
        risk_score=75,
        created_at=datetime(2026, 5, 29, 9, 0, tzinfo=timezone.utc),
    )
    outside = _event(
        action="ALLOW",
        risk_level="low",
        risk_score=5,
        created_at=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
    )
    fake_session = _FakeSession(
        events=[masked, blocked, warned, outside],
        detections=[_detection(masked, count=2), _detection(blocked, count=1), _detection(outside, count=1)],
        users=[
            _user(user_id=user_a, login_id="member01"),
            _user(user_id=user_a_alias, login_id="member01"),
            _user(user_id=user_b, login_id="member02"),
            _user(user_id=outside.user_id, login_id="outside"),
        ],
    )

    response = _client(fake_session).get("/dashboard/overview")
    body = response.json()

    assert response.status_code == 200
    assert body["event_count"] == 3
    assert body["blocked_count"] == 1
    assert body["masked_count"] == 1
    assert body["warned_count"] == 1
    assert body["allowed_count"] == 0
    assert len({masked.user_id, blocked.user_id, warned.user_id}) == 3
    assert body["active_user_count"] == 2
    assert body["content_unavailable_event_count"] == 0
    assert body["last_event_at"] is not None
    assert body["action_counts"] == [
        {"action": "allow", "count": 0},
        {"action": "warn", "count": 1},
        {"action": "mask", "count": 1},
        {"action": "block", "count": 1},
    ]
    assert body["risk_level_counts"] == [
        {"risk_level": "low", "count": 0},
        {"risk_level": "medium", "count": 1},
        {"risk_level": "high", "count": 1},
        {"risk_level": "critical", "count": 1},
    ]
    assert body["detector_category_counts"] == [{"category": "PII", "count": 3}]
    assert body["period_buckets"][-1]["bucket_start"] == "2026-05-30T00:00:00Z"
    assert body["period_buckets"][-1]["bucket_end"].startswith("2026-05-30T23:59:59")
    assert body["period_buckets"][-1]["event_count"] == 2
    assert body["period_buckets"][-1]["blocked_count"] == 1
    assert body["period_buckets"][-1]["masked_count"] == 1
    assert body["period_buckets"][-1]["warned_count"] == 0
    assert body["period_buckets"][-2]["event_count"] == 1
    assert body["period_buckets"][-2]["blocked_count"] == 0
    assert body["period_buckets"][-2]["masked_count"] == 0
    assert body["period_buckets"][-2]["warned_count"] == 1
    assert "analysis_events.created_at" in fake_session.statements[0]


def test_dashboard_overview_counts_distinct_events_with_unavailable_inputs(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_overview, "utc_today", lambda: date(2026, 5, 30))
    user_id = uuid.uuid4()
    unavailable_once = _event(
        user_id=user_id,
        action="WARN",
        risk_level="medium",
        risk_score=50,
        created_at=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
    )
    unavailable_twice = _event(
        user_id=user_id,
        action="BLOCK",
        risk_level="high",
        risk_score=80,
        created_at=datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc),
    )
    fully_scanned = _event(
        user_id=user_id,
        action="ALLOW",
        risk_level="low",
        risk_score=5,
        created_at=datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc),
    )
    outside_window = _event(
        user_id=user_id,
        action="WARN",
        risk_level="medium",
        risk_score=50,
        created_at=datetime(2026, 4, 30, 10, 0, tzinfo=timezone.utc),
    )
    fake_session = _FakeSession(
        events=[unavailable_once, unavailable_twice, fully_scanned, outside_window],
        event_inputs=[
            _event_input(
                unavailable_once,
                input_index=0,
                content_included=False,
                decision_basis="content_unavailable",
                reason="file_too_large",
            ),
            _event_input(
                unavailable_twice,
                input_index=0,
                content_included=False,
                decision_basis="content_unavailable",
                reason="unsupported_type",
            ),
            _event_input(
                unavailable_twice,
                input_index=1,
                content_included=False,
                decision_basis="content_unavailable",
                reason="file_too_large",
            ),
            _event_input(
                fully_scanned,
                input_index=0,
                content_included=True,
                decision_basis="no_detection",
            ),
            _event_input(
                outside_window,
                input_index=0,
                content_included=False,
                decision_basis="content_unavailable",
                reason="file_too_large",
            ),
        ],
        users=[_user(user_id=user_id, login_id="member01")],
    )

    response = _client(fake_session).get("/dashboard/overview")
    body = response.json()

    assert response.status_code == 200
    assert body["content_unavailable_event_count"] == 2


def test_dashboard_overview_response_excludes_private_values(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_overview, "utc_today", lambda: date(2026, 5, 30))
    event = _event(
        action="MASK",
        risk_level="medium",
        risk_score=50,
        created_at=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
    )
    response = _client(_FakeSession(events=[event], detections=[_detection(event)])).get("/dashboard/overview")
    encoded = json.dumps(response.json(), ensure_ascii=False)

    assert response.status_code == 200
    assert "abcdef1234567890abcdef1234567890" not in encoded
    assert "raw prompt" not in encoded
    assert "input text" not in encoded
    assert "raw_prompt" not in encoded
    assert "prompt_text" not in encoded
    assert "file content" not in encoded
    assert "file_content" not in encoded
    assert "raw_file_text" not in encoded
    assert "detected raw value" not in encoded
    assert "detected_raw_value" not in encoded
    assert "full masked_prompt" not in encoded
    assert "masked_prompt" not in encoded
    assert "original_filename" not in encoded
    assert "password" not in encoded
    assert "password_hash" not in encoded
    assert "token" not in encoded
    assert "secret" not in encoded
    assert "session id" not in encoded
    assert "DB URL" not in encoded
    assert "stack trace" not in encoded


def test_dashboard_overview_route_is_registered_on_main_app() -> None:
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/dashboard/overview" in paths
