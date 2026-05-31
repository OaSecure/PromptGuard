"""align v1 mvp schema tables

Revision ID: 20260531_0005
Revises: 20260530_0004
Create Date: 2026-05-31
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260531_0005"
down_revision: str | None = "20260530_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILT_IN_FILTER_RULES = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "kind": "EMAIL",
        "name": "Built-in Email Detector",
        "description": "Detects email address patterns.",
        "severity": "medium",
        "action": "MASK",
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "kind": "PHONE",
        "name": "Built-in Phone Detector",
        "description": "Detects phone number patterns.",
        "severity": "medium",
        "action": "MASK",
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "kind": "RRN",
        "name": "Built-in Resident Registration Number Detector",
        "description": "Detects Korean resident registration number patterns.",
        "severity": "high",
        "action": "MASK",
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "kind": "CARD",
        "name": "Built-in Payment Card Detector",
        "description": "Detects payment card number patterns.",
        "severity": "high",
        "action": "MASK",
    },
]


def upgrade() -> None:
    op.add_column("analysis_events", sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "analysis_events",
        sa.Column("allow_original_send", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "analysis_events",
        sa.Column("requires_user_confirmation", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "analysis_events",
        sa.Column("source_metadata", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )
    op.create_index(
        "ix_analysis_events_user_client_request",
        "analysis_events",
        ["user_id", "client_request_id"],
    )
    op.create_unique_constraint(
        "uq_analysis_events_user_client_request_id",
        "analysis_events",
        ["user_id", "client_request_id"],
    )

    op.create_table(
        "event_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("content_included", sa.Boolean(), nullable=False),
        sa.Column("content_scanned", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata_summary", sa.JSON(), nullable=False),
        sa.Column("content_unavailable_reason", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("size_bytes is null or size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "input_id", name="uq_event_inputs_event_input_id"),
    )
    op.create_index("ix_event_inputs_event_id", "event_inputs", ["event_id"])
    op.create_index("ix_event_inputs_input_id", "event_inputs", ["input_id"])
    op.create_index("ix_event_inputs_kind", "event_inputs", ["kind"])
    op.create_index("ix_event_inputs_source", "event_inputs", ["source"])

    op.add_column("event_detections", sa.Column("input_id", sa.String(length=120), nullable=True))
    op.add_column("event_detections", sa.Column("action", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_event_detections_action",
        "event_detections",
        "action is null or action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')",
    )
    op.create_index("ix_event_detections_input_id", "event_detections", ["input_id"])

    op.create_table(
        "filter_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("editable_fields", sa.JSON(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origin in ('built_in', 'custom', 'business_context')", name="ck_filter_rules_origin"),
        sa.CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_filter_rules_severity"),
        sa.CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_filter_rules_action"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filter_rules_enabled", "filter_rules", ["enabled"])
    op.create_index("ix_filter_rules_kind", "filter_rules", ["kind"])
    op.create_index("ix_filter_rules_origin", "filter_rules", ["origin"])

    filter_rules = sa.table(
        "filter_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("origin", sa.String),
        sa.column("kind", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("enabled", sa.Boolean),
        sa.column("severity", sa.String),
        sa.column("action", sa.String),
        sa.column("editable_fields", sa.JSON),
        sa.column("config_json", sa.JSON),
    )
    op.bulk_insert(
        filter_rules,
        [
            {
                "id": UUID(rule["id"]),
                "origin": "built_in",
                "kind": rule["kind"],
                "name": rule["name"],
                "description": rule["description"],
                "enabled": True,
                "severity": rule["severity"],
                "action": rule["action"],
                "editable_fields": ["enabled", "severity", "action"],
                "config_json": {},
            }
            for rule in BUILT_IN_FILTER_RULES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_filter_rules_origin", table_name="filter_rules")
    op.drop_index("ix_filter_rules_kind", table_name="filter_rules")
    op.drop_index("ix_filter_rules_enabled", table_name="filter_rules")
    op.drop_table("filter_rules")

    op.drop_index("ix_event_detections_input_id", table_name="event_detections")
    op.drop_constraint("ck_event_detections_action", "event_detections", type_="check")
    op.drop_column("event_detections", "action")
    op.drop_column("event_detections", "input_id")

    op.drop_index("ix_event_inputs_source", table_name="event_inputs")
    op.drop_index("ix_event_inputs_kind", table_name="event_inputs")
    op.drop_index("ix_event_inputs_input_id", table_name="event_inputs")
    op.drop_index("ix_event_inputs_event_id", table_name="event_inputs")
    op.drop_table("event_inputs")

    op.drop_constraint("uq_analysis_events_user_client_request_id", "analysis_events", type_="unique")
    op.drop_index("ix_analysis_events_user_client_request", table_name="analysis_events")
    op.drop_column("analysis_events", "source_metadata")
    op.drop_column("analysis_events", "requires_user_confirmation")
    op.drop_column("analysis_events", "allow_original_send")
    op.drop_column("analysis_events", "client_request_id")
