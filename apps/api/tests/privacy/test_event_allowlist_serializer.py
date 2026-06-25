import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.events import EventInput
from app.domain.types.policy import ContextRiskEvidence
from app.privacy.event_serializer import EventProjection, serialize_event_write

EVENT_ID = UUID("10000000-0000-4000-8000-000000000001")
USER_ID = UUID("20000000-0000-4000-8000-000000000001")


def _payload(item):
    return SimpleNamespace(
        client_request_id="request-1", filter_config_revision="config-1", inputs=[item],
        context=SimpleNamespace(ai_service="chatgpt", ai_service_domain="chatgpt.com", browser="chrome"),
        raw_prompt="FORBIDDEN_RAW_PROMPT", masked_prompt="FORBIDDEN_MASKED_PROMPT",
    )


def test_event_serializer_is_allowlist_only_and_filters_unknown_nested_evidence():
    item = SimpleNamespace(input_id="input-1", kind="text", source="composer", size_bytes=42,
                           content_included=True, file_ref="fref_FORBIDDEN", content="FORBIDDEN_CONTENT")
    result = SimpleNamespace(input_id="input-1", input_index=0, kind="text", source="composer",
                             content_included=True, content_scanned=True, decision_basis="detection",
                             content_unavailable_reason=None, limit_exceeded=None)
    match = SimpleNamespace(
        rule_id="rule-1", detector_id="EMAIL", action="MASK", type="EMAIL", category="PII",
        source="built_in_detector", severity="medium", confidence=100, count=1,
        reason_code="SAFE_REASON", match_count=1,
        safe_evidence={"value_lengths": [18], "raw_value": "FORBIDDEN_SECRET", "unknown": "FORBIDDEN"},
    )
    projection = serialize_event_write(
        event_id=EVENT_ID, user_id=USER_ID, login_id="user-1", payload=_payload(item), action="MASK",
        risk_score=55, risk_level="medium", input_results=[result], matched_inputs=[(0, item, [match])],
        idempotency_expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    encoded = projection.model_dump_json()
    assert "FORBIDDEN" not in encoded
    assert projection.inputs[0].size_bucket == "small"
    assert projection.detections[0].safe_evidence.value_lengths == [18]


def test_file_reference_projection_contains_safe_metadata_without_file_ref():
    item = SimpleNamespace(input_id="file-1", kind="file_reference", source="attached_file", size_bytes=42,
                           content_included=False, file_ref="fref_FORBIDDEN")
    result = SimpleNamespace(input_id="file-1", input_index=0, kind="file_reference", source="attached_file",
                             content_included=False, content_scanned=False, decision_basis="content_unavailable",
                             content_unavailable_reason="unavailable", limit_exceeded=None)
    projection = serialize_event_write(
        event_id=EVENT_ID, user_id=USER_ID, login_id="user-1", payload=_payload(item), action="BLOCK",
        risk_score=95, risk_level="critical", input_results=[result], matched_inputs=[],
        idempotency_expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert projection.inputs[0].kind == "file_reference"
    assert projection.inputs[0].content_scanned is False
    assert "file_ref" not in type(projection.inputs[0]).model_fields


def test_context_risk_projection_is_raw_free_event_metadata():
    item = SimpleNamespace(input_id="input-1", kind="text", source="composer", size_bytes=42,
                           content_included=True, content="FORBIDDEN_CONTENT")
    result = SimpleNamespace(input_id="input-1", input_index=0, kind="text", source="composer",
                             content_included=True, content_scanned=True, decision_basis="context_risk",
                             content_unavailable_reason=None, limit_exceeded=None)
    projection = serialize_event_write(
        event_id=EVENT_ID, user_id=USER_ID, login_id="user-1", payload=_payload(item), action="WARN",
        risk_score=40, risk_level="medium", input_results=[result], matched_inputs=[],
        context_risk_evidence=ContextRiskEvidence(
            enabled=True,
            status="candidate",
            candidate_count=1,
            accepted_count=0,
            labels=["INTERNAL_OPERATION_CONTEXT"],
            reason_code="RISK_CONTEXT_LR_ONLY",
        ),
        idempotency_expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    encoded = projection.model_dump_json()
    assert "FORBIDDEN" not in encoded
    assert projection.detections == []
    assert projection.inputs[0].decision_basis == "context_risk"
    assert projection.event.context_risk_evidence == {
        "enabled": True,
        "status": "candidate",
        "candidate_count": 1,
        "accepted_count": 0,
        "labels": ["INTERNAL_OPERATION_CONTEXT"],
        "status_counts": {},
        "highest_score_bucket": None,
        "highest_confidence_bucket": None,
        "failure_code": None,
        "reason_code": "RISK_CONTEXT_LR_ONLY",
        "classifier_model_versions": [],
        "verifier_model_versions": [],
    }


def test_persistence_dtos_reject_unknown_fields_and_orm_has_no_exact_size():
    with pytest.raises(ValidationError):
        EventProjection(
            id=EVENT_ID, user_id=USER_ID, login_id="user", client_request_id="req", action="ALLOW",
            risk_score=0, risk_level="low", filter_config_revision="cfg", service="chatgpt",
            service_domain="chatgpt.com", platform="chrome", context_risk_evidence=None, raw_prompt="forbidden",
        )
    assert "size_bytes" not in EventInput.__table__.columns
    assert "size_bucket" in EventInput.__table__.columns
