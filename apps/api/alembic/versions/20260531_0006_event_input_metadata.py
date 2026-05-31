"""add event input metadata schema

Revision ID: 20260531_0006
Revises: 20260530_0005
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260531_0006"
down_revision: str | None = "20260530_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_events", sa.Column("login_id", sa.String(length=120), nullable=True))
    op.add_column("analysis_events", sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        "ix_analysis_events_login_client_request_id",
        "analysis_events",
        ["login_id", "client_request_id"],
        unique=False,
    )

    op.create_table(
        "event_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_id", sa.String(length=80), nullable=False),
        sa.Column("input_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_included", sa.Boolean(), nullable=False),
        sa.Column("content_scanned", sa.Boolean(), nullable=False),
        sa.Column("decision_basis", sa.String(length=40), nullable=False),
        sa.Column("content_unavailable_reason", sa.String(length=120), nullable=True),
        sa.Column("limit_exceeded", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_index >= 0", name="ck_event_inputs_input_index_non_negative"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        sa.CheckConstraint(
            "decision_basis in ('detection', 'no_detection', 'metadata_only', 'content_unavailable')",
            name="ck_event_inputs_decision_basis",
        ),
        sa.CheckConstraint(
            "limit_exceeded is null or limit_exceeded in ("
            "'MAX_ANALYZE_REQUEST_BYTES', "
            "'MAX_COMPOSER_TEXT_BYTES', "
            "'MAX_FILE_TEXT_SCAN_BYTES', "
            "'MAX_CONVERTED_PASTE_TEXT_BYTES'"
            ")",
            name="ck_event_inputs_limit_exceeded",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_inputs_event_id", "event_inputs", ["event_id"])
    op.create_index("ix_event_inputs_event_input", "event_inputs", ["event_id", "input_id"])

    op.add_column("event_detections", sa.Column("input_id", sa.String(length=80), nullable=True))
    op.add_column("event_detections", sa.Column("input_index", sa.Integer(), nullable=True))
    op.add_column("event_detections", sa.Column("kind", sa.String(length=40), nullable=True))
    op.add_column("event_detections", sa.Column("filter_rule_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("event_detections", sa.Column("detector_id", sa.String(length=120), nullable=True))
    op.add_column("event_detections", sa.Column("action", sa.String(length=20), nullable=True))
    op.add_column("event_detections", sa.Column("placeholder", sa.String(length=80), nullable=True))
    op.add_column(
        "event_detections",
        sa.Column("matched_keywords", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.add_column(
        "event_detections",
        sa.Column("evidence_counts", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )
    op.create_check_constraint(
        "ck_event_detections_action",
        "event_detections",
        "action is null or action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')",
    )
    op.create_index("ix_event_detections_event_input", "event_detections", ["event_id", "input_id"])

    op.alter_column("event_detections", "matched_keywords", server_default=None)
    op.alter_column("event_detections", "evidence_counts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_event_detections_event_input", table_name="event_detections")
    op.drop_constraint("ck_event_detections_action", "event_detections", type_="check")
    op.drop_column("event_detections", "evidence_counts")
    op.drop_column("event_detections", "matched_keywords")
    op.drop_column("event_detections", "placeholder")
    op.drop_column("event_detections", "action")
    op.drop_column("event_detections", "detector_id")
    op.drop_column("event_detections", "filter_rule_id")
    op.drop_column("event_detections", "kind")
    op.drop_column("event_detections", "input_index")
    op.drop_column("event_detections", "input_id")

    op.drop_index("ix_event_inputs_event_input", table_name="event_inputs")
    op.drop_index("ix_event_inputs_event_id", table_name="event_inputs")
    op.drop_table("event_inputs")

    op.drop_index("ix_analysis_events_login_client_request_id", table_name="analysis_events")
    op.drop_column("analysis_events", "client_request_id")
    op.drop_column("analysis_events", "login_id")
