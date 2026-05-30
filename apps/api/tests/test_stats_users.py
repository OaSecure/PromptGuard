import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.auth import User
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
    def __init__(self, *, users=None, events=None, detections=None):
        self.users = list(users or [])
        self.events = list(events or [])
        self.detections = list(detections or [])
        self.statements = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "FROM users" in statement_text:
            return _ExecuteResult(self.users)
        if "FROM analysis_events" in statement_text:
            return _ExecuteResult(self.events)
        if "FROM event_detections" in statement_text:
            return _ExecuteResult(self.detections)
        return _ExecuteResult([])


def _user(
    *,
    username: str,
    status_value: str = "ACTIVE",
    last_event_at: datetime | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        login_id=username,
        login_id_normalized=username.casefold(),
        username=username,
        email=None,
        email_normalized=None,
        department="Security",
        display_name=f"{username} display",
        role="USER",
        status=status_value,
        password_hash="hash",
        password_hash_algorithm="argon2id",
        password_hash_params=None,
        last_event_at=last_event_at,
    )


def _event(
    user: User,
    *,
    action: str,
    created_at: datetime,
    risk_level: str = "medium",
    risk_score: int = 55,
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
        created_at=created_at,
    )


def _detection(event: AnalysisEvent, *, category: str, detection_type: str, count: int = 1) -> EventDetection:
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


def test_user_stats_requires_admin_access() -> None:
    fake_session = _FakeSession(users=[_user(username="alpha")])

    assert _client(fake_session, role=None).get("/stats/users").status_code == 401
    assert _client(fake_session, role="USER").get("/stats/users").status_code == 403
    assert _client(fake_session, role="ADMIN").get("/stats/users").status_code == 200


def test_user_stats_returns_zero_counts_for_users_without_events() -> None:
    user = _user(username="empty")
    response = _client(_FakeSession(users=[user])).get("/stats/users")
    body = response.json()

    assert response.status_code == 200
    assert body == [
        {
            "user_id": str(user.id),
            "login_id": "empty",
            "username": "empty",
            "display_name": "empty display",
            "department": "Security",
            "role": "USER",
            "status": "ACTIVE",
            "last_event_at": None,
            "event_count": 0,
            "blocked_count": 0,
            "masked_count": 0,
            "warned_count": 0,
            "allowed_count": 0,
            "action_distribution": {},
            "detection_distribution": {},
            "top_detector_category": None,
        }
    ]


def test_user_stats_aggregates_actions_and_detections() -> None:
    user = _user(username="alpha")
    other = _user(username="beta")
    masked = _event(user, action="MASK", created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc))
    blocked = _event(user, action="BLOCK", created_at=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc), risk_score=95)
    warned = _event(user, action="WARN", created_at=datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc))
    allowed = _event(other, action="ALLOW", created_at=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc), risk_score=0)
    fake_session = _FakeSession(
        users=[user, other],
        events=[masked, blocked, warned, allowed],
        detections=[
            _detection(masked, category="PII", detection_type="EMAIL", count=2),
            _detection(blocked, category="PAYMENT", detection_type="CARD", count=1),
            _detection(warned, category="PII", detection_type="PHONE", count=1),
        ],
    )

    response = _client(fake_session).get("/stats/users")
    body = response.json()
    alpha = body[0]
    beta = body[1]
    encoded = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert alpha["user_id"] == str(user.id)
    assert alpha["event_count"] == 3
    assert alpha["blocked_count"] == 1
    assert alpha["masked_count"] == 1
    assert alpha["warned_count"] == 1
    assert alpha["allowed_count"] == 0
    assert alpha["action_distribution"] == {"WARN": 1, "MASK": 1, "BLOCK": 1}
    assert alpha["detection_distribution"] == {"CARD": 1, "EMAIL": 2, "PHONE": 1}
    assert alpha["top_detector_category"] == "PII"
    assert alpha["last_event_at"] == "2026-05-30T14:00:00Z"
    assert beta["event_count"] == 1
    assert beta["allowed_count"] == 1
    assert "abcdef1234567890abcdef1234567890" not in encoded
    assert "raw_prompt" not in encoded
    assert "masked_prompt" not in encoded
    assert "raw_detected_value" not in encoded
    assert "prompt_text" not in encoded
    assert "file_content" not in encoded


def test_user_stats_breaks_top_category_ties_by_name() -> None:
    user = _user(username="tie")
    event = _event(user, action="MASK", created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc))
    fake_session = _FakeSession(
        users=[user],
        events=[event],
        detections=[
            _detection(event, category="PAYMENT", detection_type="CARD", count=1),
            _detection(event, category="PII", detection_type="EMAIL", count=1),
        ],
    )

    body = _client(fake_session).get("/stats/users").json()

    assert body[0]["top_detector_category"] == "PAYMENT"


def test_user_stats_filters_disabled_users_and_applies_limit() -> None:
    active_one = _user(username="active-one")
    active_two = _user(username="active-two")
    disabled = _user(username="disabled", status_value="DISABLED")
    events = [
        _event(active_one, action="MASK", created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)),
        _event(active_one, action="MASK", created_at=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc)),
        _event(active_two, action="ALLOW", created_at=datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc), risk_score=0),
        _event(disabled, action="BLOCK", created_at=datetime(2026, 5, 30, 15, 0, tzinfo=timezone.utc), risk_score=95),
    ]
    fake_session = _FakeSession(users=[active_two, disabled, active_one], events=events)

    response = _client(fake_session).get("/stats/users?include_disabled=false&limit=1")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["user_id"] == str(active_one.id)
    assert body[0]["event_count"] == 2
