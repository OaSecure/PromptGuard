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
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prompt_hash: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_hash_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    allow_original_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_user_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filter_rule_set_version: Mapped[str] = mapped_column(String(80), nullable=False)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    service_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    inputs: Mapped[list["EventInput"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    detections: Mapped[list["EventDetection"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_analysis_events_action"),
        CheckConstraint("risk_level in ('low', 'medium', 'high', 'critical')", name="ck_analysis_events_risk_level"),
        CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_analysis_events_risk_score_range"),
        Index("ix_analysis_events_user_created_at", "user_id", "created_at"),
        Index("ix_analysis_events_user_client_request", "user_id", "client_request_id"),
        Index("ix_analysis_events_action_created_at", "action", "created_at"),
        Index("ix_analysis_events_created_at", "created_at"),
        UniqueConstraint("user_id", "client_request_id", name="uq_analysis_events_user_client_request_id"),
    )


class EventInput(Base):
    __tablename__ = "event_inputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_events.id", ondelete="CASCADE"),
    )
    input_id: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    content_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_scanned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_unavailable_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped[AnalysisEvent] = relationship(back_populates="inputs")

    __table_args__ = (
        CheckConstraint("size_bytes is null or size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        UniqueConstraint("event_id", "input_id", name="uq_event_inputs_event_input_id"),
        Index("ix_event_inputs_event_id", "event_id"),
        Index("ix_event_inputs_input_id", "input_id"),
        Index("ix_event_inputs_kind", "kind"),
        Index("ix_event_inputs_source", "source"),
    )


class EventDetection(Base):
    __tablename__ = "event_detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_events.id", ondelete="CASCADE"),
    )
    input_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped[AnalysisEvent] = relationship(back_populates="detections")

    __table_args__ = (
        CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_event_detections_severity"),
        CheckConstraint(
            "action is null or action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')",
            name="ck_event_detections_action",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 100", name="ck_event_detections_confidence_range"),
        CheckConstraint("count >= 0", name="ck_event_detections_count_non_negative"),
        CheckConstraint("match_count >= 0", name="ck_event_detections_match_count_non_negative"),
        Index("ix_event_detections_event_id", "event_id"),
        Index("ix_event_detections_input_id", "input_id"),
        Index("ix_event_detections_type", "type"),
        Index("ix_event_detections_category", "category"),
    )
