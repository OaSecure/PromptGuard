"""add MVP readiness metadata tables

Revision ID: 20260601_0008
Revises: 20260601_0007
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260601_0008"
down_revision: str | None = "20260601_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_id", sa.String(length=120), nullable=False),
        sa.Column("input_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_included", sa.Boolean(), nullable=False),
        sa.Column("content_scanned", sa.Boolean(), nullable=False),
        sa.Column("decision_basis", sa.String(length=80), nullable=False),
        sa.Column("content_unavailable_reason", sa.String(length=120), nullable=True),
        sa.Column("limit_exceeded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_index >= 0", name="ck_event_inputs_input_index_non_negative"),
        sa.CheckConstraint("size_bytes is null or size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_inputs_event_id", "event_inputs", ["event_id"])
    op.create_index("ix_event_inputs_event_input", "event_inputs", ["event_id", "input_index"])

    op.add_column("event_detections", sa.Column("input_id", sa.String(length=120), nullable=True))
    op.add_column("event_detections", sa.Column("input_index", sa.Integer(), nullable=True))
    op.add_column("event_detections", sa.Column("kind", sa.String(length=40), nullable=True))
    op.add_column("event_detections", sa.Column("input_source", sa.String(length=80), nullable=True))
    op.add_column("event_detections", sa.Column("filter_rule_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("event_detections", sa.Column("action", sa.String(length=20), nullable=True))
    op.add_column("event_detections", sa.Column("matched_keywords", sa.JSON(), nullable=True))
    op.add_column("event_detections", sa.Column("evidence_counts", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_event_detections_filter_rule_id",
        "event_detections",
        "filter_rules",
        ["filter_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_event_detections_input_index_non_negative",
        "event_detections",
        "input_index is null or input_index >= 0",
    )
    op.create_check_constraint(
        "ck_event_detections_action",
        "event_detections",
        "action is null or action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')",
    )
    op.create_index("ix_event_detections_filter_rule_id", "event_detections", ["filter_rule_id"])
    op.create_index("ix_event_detections_event_input", "event_detections", ["event_id", "input_index"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_id", sa.String(length=80), nullable=False),
        sa.Column("client_request_id", sa.String(length=160), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_id", "client_request_id", name="uq_idempotency_keys_login_request"),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_login_id", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_actor_created_at", "audit_logs", ["actor_login_id", "created_at"])
    op.create_index("ix_audit_logs_action_created_at", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_event_inputs_event_input", table_name="event_inputs")
    op.drop_index("ix_event_inputs_event_id", table_name="event_inputs")
    op.drop_table("event_inputs")

    op.drop_index("ix_event_detections_event_input", table_name="event_detections")
    op.drop_index("ix_event_detections_filter_rule_id", table_name="event_detections")
    op.drop_constraint("ck_event_detections_action", "event_detections", type_="check")
    op.drop_constraint("ck_event_detections_input_index_non_negative", "event_detections", type_="check")
    op.drop_constraint("fk_event_detections_filter_rule_id", "event_detections", type_="foreignkey")
    op.drop_column("event_detections", "evidence_counts")
    op.drop_column("event_detections", "matched_keywords")
    op.drop_column("event_detections", "action")
    op.drop_column("event_detections", "filter_rule_id")
    op.drop_column("event_detections", "input_source")
    op.drop_column("event_detections", "kind")
    op.drop_column("event_detections", "input_index")
    op.drop_column("event_detections", "input_id")
