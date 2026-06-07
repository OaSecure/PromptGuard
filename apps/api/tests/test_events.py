import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.auth import User
from app.models.events import AnalysisEvent, EventDetection
from app.routes import events


class _ScalarResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _ExecuteResult:
    def __init__(self, *, rows=None, scalars=None, one=None):
        self.rows = rows or []
        self.scalar_items = scalars or []
        self.one = one

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.one

    def scalars(self):
        return _ScalarResult(self.scalar_items)


class _FakeSession:
    def __init__(self, rows=None, detections=None):
        self.rows = list(rows or [])
        self.detections = list(detections or [])
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "event_detections" in statement_text:
            return _ExecuteResult(scalars=self.detections)

        params = statement.compile().params
        rows = self.rows
        if "action_1" in params:
            rows = [(event, user) for event, user in rows if event.action == params["action_1"]]
        if "risk_level_1" in params:
            rows = [(event, user) for event, user in rows if event.risk_level == params["risk_level_1"]]
        if "user_id_1" in params:
            rows = [(event, user) for event, user in rows if event.user_id == params["user_id_1"]]
        if "analysis_events.id =" in statement_text:
            event_id = next((value for key, value in params.items() if key.startswith("id_")), None)
            row = next(((event, user) for event, user in rows if event_id is None or event.id == event_id), None)
            return _ExecuteResult(one=row)

        rows = sorted(rows, key=lambda row: row[0].created_at, reverse=True)
        if "param_1" in params:
            rows = rows[: params["param_1"]]
        return _ExecuteResult(rows=rows)


def _user(role: str = "ADMIN") -> User:
    return User(
        id=uuid.uuid4(),
        login_id=f"{role.lower()}-{uuid.uuid4().hex[:6]}",
        login_id_normalized=role.lower(),
        username=role.lower(),
        email=None,
        email_normalized=None,
        department="Security",
        display_name=f"PromptGuard {role}",
        role=role,
        status="ACTIVE",
        password_hash="hash",
        password_hash_algorithm="argon2id",
        password_hash_params=None,
    )


def _event(
    user: User,
    *,
    action: str = "MASK",
    risk_level: str = "medium",
    risk_score: int = 55,
    created_at: datetime | None = None,
) -> AnalysisEvent:
    return AnalysisEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        prompt_hash="abcdef1234567890abcdef1234567890",
        prompt_hash_key_id="dev-key-1",
        action=action,
        risk_score=risk_score,
        risk_level=risk_level,
        filter_rule_set_version="built-in:2026-05-30",
        service="ChatGPT",
        service_domain="chat.openai.com",
        platform="web",
        created_at=created_at or datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )


def _detection(event: AnalysisEvent, detection_type: str = "EMAIL") -> EventDetection:
    return EventDetection(
        id=uuid.uuid4(),
        event_id=event.id,
        category="PII",
        type=detection_type,
        source="built_in_detector",
        severity="medium",
        confidence=100,
        count=1,
        reason_code=f"PII_{detection_type}_DETECTED",
        match_count=1,
        safe_evidence={"value_lengths": [16]},
    )


def _client(fake_session: _FakeSession, *, role: str | None = "ADMIN") -> TestClient:
    app = FastAPI()
    app.include_router(events.router)

    async def override_session():
        yield fake_session

    async def override_admin():
        if role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
        if role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return SimpleNamespace(id=uuid.uuid4(), role=role, status="ACTIVE")

    app.dependency_overrides[events.get_db_session] = override_session
    app.dependency_overrides[events.require_admin] = override_admin
    return TestClient(app)


def test_events_require_admin_access() -> None:
    event_user = _user()
    event = _event(event_user)
    fake_session = _FakeSession(rows=[(event, event_user)])

    assert _client(fake_session, role=None).get("/events").status_code == 401
    assert _client(fake_session, role="USER").get("/events").status_code == 403
    assert _client(fake_session, role="ADMIN").get("/events").status_code == 200


def test_list_events_returns_metadata_only_latest_first() -> None:
    event_user = _user()
    older = _event(event_user, created_at=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc))
    newer = _event(event_user, action="ALLOW", risk_level="low", risk_score=0)
    fake_session = _FakeSession(rows=[(older, event_user), (newer, event_user)], detections=[_detection(older)])

    response = _client(fake_session).get("/events")
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert [item["event_id"] for item in body] == [str(newer.id), str(older.id)]
    assert body[0]["detection_count"] == 0
    assert body[1]["detection_type"] == "EMAIL"
    assert body[1]["detection_category"] == "PII"
    assert body[1]["detection_count"] == 1
    assert body[1]["detail_available"] is True
    assert "abcdef1234567890abcdef1234567890" not in encoded
    assert "raw_prompt" not in encoded
    assert "masked_prompt" not in encoded
    assert "raw_detected_value" not in encoded
    assert "prompt_text" not in encoded
    assert "file_content" not in encoded


def test_list_events_filters_action_risk_user_and_limit() -> None:
    user_a = _user()
    user_b = _user()
    masked = _event(user_a, action="MASK", risk_level="medium")
    allowed = _event(user_b, action="ALLOW", risk_level="low", risk_score=0)
    blocked = _event(user_a, action="BLOCK", risk_level="critical", risk_score=95)
    fake_session = _FakeSession(rows=[(masked, user_a), (allowed, user_b), (blocked, user_a)])

    response = _client(fake_session).get(f"/events?action=MASK&risk_level=medium&user_id={user_a.id}&limit=1")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["event_id"] == str(masked.id)
    assert "analysis_events.action" in fake_session.statements[0]
    assert "analysis_events.risk_level" in fake_session.statements[0]
    assert "analysis_events.user_id" in fake_session.statements[0]


def test_get_event_returns_detail_without_raw_values() -> None:
    event_user = _user()
    event = _event(event_user)
    detection = _detection(event)
    fake_session = _FakeSession(rows=[(event, event_user)], detections=[detection])

    response = _client(fake_session).get(f"/events/{event.id}")
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["event_id"] == str(event.id)
    assert body["platform"] == "web"
    assert "prompt_hash_prefix" not in body
    assert body["detection_summary"] == [{"category": "PII", "type": "EMAIL", "count": 1}]
    assert body["detections"][0]["safe_evidence"] == {"value_lengths": [16]}
    assert "abcdef1234567890abcdef1234567890" not in encoded
    assert "raw_prompt" not in encoded
    assert "masked_prompt" not in encoded
    assert "raw_detected_value" not in encoded
    assert "prompt_hash_prefix" not in encoded


def test_get_event_whitelists_safe_evidence_shape() -> None:
    event_user = _user()
    event = _event(event_user)
    detection = _detection(event)
    detection.safe_evidence = {
        "value_lengths": [16, -1, "bad", 32],
        "raw_value": "admin@example.com",
        "prompt_excerpt": "secret prompt excerpt",
    }
    fake_session = _FakeSession(rows=[(event, event_user)], detections=[detection])

    response = _client(fake_session).get(f"/events/{event.id}")
    body = response.json()
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["detections"][0]["safe_evidence"] == {"value_lengths": [16, 32]}
    assert "admin@example.com" not in encoded
    assert "secret prompt excerpt" not in encoded
    assert "raw_value" not in encoded
    assert "prompt_excerpt" not in encoded


def test_get_event_returns_404_for_missing_event() -> None:
    response = _client(_FakeSession()).get(f"/events/{uuid.uuid4()}")

    assert response.status_code == 404
