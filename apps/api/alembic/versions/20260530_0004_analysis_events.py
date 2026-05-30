"""add analysis event metadata tables

Revision ID: 20260530_0004
Revises: 20260528_0003
Create Date: 2026-05-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260530_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_hash", sa.String(length=160), nullable=False),
        sa.Column("prompt_hash_key_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("filter_rule_set_version", sa.String(length=80), nullable=False),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("service_domain", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_analysis_events_action"),
        sa.CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_analysis_events_risk_level",
        ),
        sa.CheckConstraint(
            "risk_score >= 0 and risk_score <= 100",
            name="ck_analysis_events_risk_score_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_events_action_created_at", "analysis_events", ["action", "created_at"])
    op.create_index("ix_analysis_events_created_at", "analysis_events", ["created_at"])
    op.create_index("ix_analysis_events_user_created_at", "analysis_events", ["user_id", "created_at"])

    op.create_table(
        "event_detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("safe_evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_event_detections_severity",
        ),
        sa.CheckConstraint(
            "confidence >= 0 and confidence <= 100",
            name="ck_event_detections_confidence_range",
        ),
        sa.CheckConstraint("count >= 0", name="ck_event_detections_count_non_negative"),
        sa.CheckConstraint("match_count >= 0", name="ck_event_detections_match_count_non_negative"),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_detections_category", "event_detections", ["category"])
    op.create_index("ix_event_detections_event_id", "event_detections", ["event_id"])
    op.create_index("ix_event_detections_type", "event_detections", ["type"])


def downgrade() -> None:
    op.drop_index("ix_event_detections_type", table_name="event_detections")
    op.drop_index("ix_event_detections_event_id", table_name="event_detections")
    op.drop_index("ix_event_detections_category", table_name="event_detections")
    op.drop_table("event_detections")

    op.drop_index("ix_analysis_events_user_created_at", table_name="analysis_events")
    op.drop_index("ix_analysis_events_created_at", table_name="analysis_events")
    op.drop_index("ix_analysis_events_action_created_at", table_name="analysis_events")
    op.drop_table("analysis_events")
