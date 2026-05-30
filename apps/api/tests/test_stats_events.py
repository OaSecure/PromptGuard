import json
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.events import AnalysisEvent, EventDetection
from app.routes import stats


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


class _FakeSession:
    def __init__(self, *, events=None, detections=None):
        self.events = list(events or [])
        self.detections = list(detections or [])
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "FROM analysis_events" in statement_text:
            return _ExecuteResult(self.events)
        if "FROM event_detections" in statement_text:
            return _ExecuteResult(self.detections)
        return _ExecuteResult([])


def _event(
    *,
    user_id: uuid.UUID | None = None,
    action: str,
    risk_level: str,
    created_at: datetime,
) -> AnalysisEvent:
    return AnalysisEvent(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        prompt_hash="abcdef1234567890abcdef1234567890",
        prompt_hash_key_id="dev-key-1",
        action=action,
        risk_score=55,
        risk_level=risk_level,
        filter_rule_set_version="built-in:2026-05-30",
        service="ChatGPT",
        service_domain="chat.openai.com",
        platform="web",
        created_at=created_at,
    )


def _detection(event: AnalysisEvent, *, category: str, detection_type: str, count: int) -> EventDetection:
    return EventDetection(
        id=uuid.uuid4(),
        event_id=event.id,
        category=category,
        type=detection_type,
        source="built_in_detector",
        severity="medium",
        confidence=100,
        count=count,
        reason_code=f"{category}_{detection_type}_DETECTED",
        match_count=count,
        safe_evidence={"value_lengths": [16] * count},
    )


def _client(fake_session: _FakeSession, *, role: str | None = "ADMIN") -> TestClient:
    app = FastAPI()
    app.include_router(stats.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
        if role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return SimpleNamespace(id=uuid.uuid4(), role=role, status="ACTIVE")

    app.dependency_overrides[stats.get_db_session] = override_session
    app.dependency_overrides[stats.require_admin] = override_admin
    return TestClient(app)


def test_event_stats_requires_admin_access() -> None:
    fake_session = _FakeSession()

    assert _client(fake_session, role=None).get("/stats/events").status_code == 401
    assert _client(fake_session, role="USER").get("/stats/events").status_code == 403
    assert _client(fake_session, role="ADMIN").get("/stats/events").status_code == 200


def test_event_stats_aggregates_chart_metadata() -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    masked = _event(
        user_id=user_a,
        action="MASK",
        risk_level="medium",
        created_at=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
    )
    blocked = _event(
        user_id=user_a,
        action="BLOCK",
        risk_level="critical",
        created_at=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
    )
    allowed = _event(
        user_id=user_b,
        action="ALLOW",
        risk_level="low",
        created_at=datetime(2026, 5, 29, 9, 0, tzinfo=timezone.utc),
    )
    fake_session = _FakeSession(
        events=[masked, blocked, allowed],
        detections=[
            _detection(masked, category="PII", detection_type="EMAIL", count=2),
            _detection(masked, category="PII", detection_type="PHONE", count=1),
            _detection(blocked, category="PAYMENT", detection_type="CARD", count=1),
        ],
    )

    response = _client(fake_session).get("/stats/events?days=30")
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["event_count"] == 3
    assert body["active_user_count"] == 2
    assert body["action_distribution"] == {"ALLOW": 1, "MASK": 1, "BLOCK": 1}
    assert body["risk_level_distribution"] == {"low": 1, "medium": 1, "critical": 1}
    assert body["detection_type_distribution"] == {"CARD": 1, "EMAIL": 2, "PHONE": 1}
    assert body["detection_category_distribution"] == {"PAYMENT": 1, "PII": 3}
    assert len(body["daily_buckets"]) == 30
    assert "abcdef1234567890abcdef1234567890" not in encoded
    assert "raw_prompt" not in encoded
    assert "masked_prompt" not in encoded
    assert "raw_detected_value" not in encoded
    assert "prompt_text" not in encoded
    assert "file_content" not in encoded


def test_event_stats_helper_includes_empty_daily_buckets() -> None:
    event = _event(
        action="MASK",
        risk_level="medium",
        created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )

    result = stats.event_stats_response(
        events=[event],
        detections=[],
        days=3,
        as_of=date(2026, 5, 30),
    )

    assert [bucket.date for bucket in result.daily_buckets] == ["2026-05-28", "2026-05-29", "2026-05-30"]
    assert [bucket.event_count for bucket in result.daily_buckets] == [0, 0, 1]
    assert result.daily_buckets[0].action_distribution == {}
    assert result.daily_buckets[2].action_distribution == {"MASK": 1}
    assert result.daily_buckets[2].risk_level_distribution == {"medium": 1}


def test_event_stats_excludes_events_and_detections_outside_window() -> None:
    inside = _event(
        action="WARN",
        risk_level="high",
        created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )
    outside = _event(
        action="BLOCK",
        risk_level="critical",
        created_at=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
    )

    result = stats.event_stats_response(
        events=[inside, outside],
        detections=[
            _detection(inside, category="PII", detection_type="EMAIL", count=1),
            _detection(outside, category="PAYMENT", detection_type="CARD", count=1),
        ],
        days=2,
        as_of=date(2026, 5, 30),
    )

    assert result.event_count == 1
    assert result.action_distribution == {"WARN": 1}
    assert result.risk_level_distribution == {"high": 1}
    assert result.detection_type_distribution == {"EMAIL": 1}
    assert result.detection_category_distribution == {"PII": 1}


def test_event_stats_validates_days_range() -> None:
    client = _client(_FakeSession())

    assert client.get("/stats/events?days=1").status_code == 200
    assert client.get("/stats/events?days=90").status_code == 200
    assert client.get("/stats/events?days=0").status_code == 422
    assert client.get("/stats/events?days=91").status_code == 422
