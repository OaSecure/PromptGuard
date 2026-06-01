import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    prompt_hash: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_hash_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    filter_rule_set_version: Mapped[str] = mapped_column(String(80), nullable=False)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    service_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    detections: Mapped[list["EventDetection"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    inputs: Mapped[list["EventInput"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_analysis_events_action"),
        CheckConstraint("risk_level in ('low', 'medium', 'high', 'critical')", name="ck_analysis_events_risk_level"),
        CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_analysis_events_risk_score_range"),
        Index("ix_analysis_events_user_created_at", "user_id", "created_at"),
        Index("ix_analysis_events_action_created_at", "action", "created_at"),
        Index("ix_analysis_events_created_at", "created_at"),
    )


class EventInput(Base):
    __tablename__ = "event_inputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_events.id", ondelete="CASCADE"),
    )
    input_id: Mapped[str] = mapped_column(String(120), nullable=False)
    input_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_scanned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_basis: Mapped[str] = mapped_column(String(80), nullable=False)
    content_unavailable_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    limit_exceeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped[AnalysisEvent] = relationship(back_populates="inputs")

    __table_args__ = (
        CheckConstraint("input_index >= 0", name="ck_event_inputs_input_index_non_negative"),
        CheckConstraint("size_bytes is null or size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        Index("ix_event_inputs_event_id", "event_id"),
        Index("ix_event_inputs_event_input", "event_id", "input_index"),
    )


class EventDetection(Base):
    __tablename__ = "event_detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_events.id", ondelete="CASCADE"),
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    input_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    filter_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("filter_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    evidence_counts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    safe_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped[AnalysisEvent] = relationship(back_populates="detections")

    __table_args__ = (
        CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_event_detections_severity"),
        CheckConstraint("confidence >= 0 and confidence <= 100", name="ck_event_detections_confidence_range"),
        CheckConstraint("count >= 0", name="ck_event_detections_count_non_negative"),
        CheckConstraint("match_count >= 0", name="ck_event_detections_match_count_non_negative"),
        CheckConstraint("input_index is null or input_index >= 0", name="ck_event_detections_input_index_non_negative"),
        CheckConstraint(
            "action is null or action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')",
            name="ck_event_detections_action",
        ),
        Index("ix_event_detections_event_id", "event_id"),
        Index("ix_event_detections_event_input", "event_id", "input_index"),
        Index("ix_event_detections_filter_rule_id", "filter_rule_id"),
        Index("ix_event_detections_type", "type"),
        Index("ix_event_detections_category", "category"),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login_id: Mapped[str] = mapped_column(String(80), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("login_id", "client_request_id", name="uq_idempotency_keys_login_request"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_login_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_actor_created_at", "actor_login_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
    )
