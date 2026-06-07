"""Add event input metadata.

Revision ID: 20260607_0008
Revises: 20260601_0007
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260607_0008"
down_revision: Union[str, None] = "20260601_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_events", sa.Column("login_id", sa.String(length=80), nullable=True))
    op.add_column("analysis_events", sa.Column("client_request_id", sa.String(length=128), nullable=True))
    op.add_column("analysis_events", sa.Column("filter_config_revision", sa.String(length=80), nullable=True))
    op.alter_column("analysis_events", "prompt_hash", existing_type=sa.String(length=160), nullable=True)
    op.alter_column("analysis_events", "prompt_hash_key_id", existing_type=sa.String(length=80), nullable=True)
    op.alter_column("analysis_events", "filter_rule_set_version", existing_type=sa.String(length=80), nullable=True)
    op.create_index("ix_analysis_events_login_created_at", "analysis_events", ["login_id", "created_at"])
    op.create_index("ix_analysis_events_client_request", "analysis_events", ["login_id", "client_request_id"])

    op.create_table(
        "event_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_id", sa.String(length=80), nullable=False),
        sa.Column("input_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_included", sa.Boolean(), nullable=False),
        sa.Column("content_scanned", sa.Boolean(), nullable=False),
        sa.Column("decision_basis", sa.String(length=40), nullable=False),
        sa.Column("content_unavailable_reason", sa.String(length=40), nullable=True),
        sa.Column("limit_exceeded", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_index >= 0", name="ck_event_inputs_input_index_non_negative"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_event_inputs_size_bytes_non_negative"),
        sa.CheckConstraint(
            "kind in ('text', 'attachment_metadata', 'unsupported_attachment')",
            name="ck_event_inputs_kind",
        ),
        sa.CheckConstraint(
            "source in ('composer', 'converted_paste', 'file', 'attachment_chip')",
            name="ck_event_inputs_source",
        ),
        sa.CheckConstraint(
            "decision_basis in ('no_detection', 'detection', 'content_unavailable', 'metadata_only')",
            name="ck_event_inputs_decision_basis",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["analysis_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_inputs_event_id", "event_inputs", ["event_id"])
    op.create_index("ix_event_inputs_event_input_index", "event_inputs", ["event_id", "input_index"])
    op.create_index("ix_event_inputs_input_id", "event_inputs", ["input_id"])

    op.add_column("event_detections", sa.Column("input_id", sa.String(length=80), nullable=True))
    op.add_column("event_detections", sa.Column("input_index", sa.Integer(), nullable=True))
    op.add_column("event_detections", sa.Column("kind", sa.String(length=40), nullable=True))
    op.add_column("event_detections", sa.Column("input_source", sa.String(length=40), nullable=True))
    op.add_column("event_detections", sa.Column("filter_rule_id", sa.String(length=80), nullable=True))
    op.add_column("event_detections", sa.Column("detector_id", sa.String(length=80), nullable=True))
    op.add_column("event_detections", sa.Column("action", sa.String(length=20), nullable=True))
    op.add_column("event_detections", sa.Column("placeholder", sa.String(length=120), nullable=True))
    op.add_column("event_detections", sa.Column("matched_keywords", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("event_detections", sa.Column("evidence_counts", sa.JSON(), nullable=False, server_default="{}"))
    op.create_check_constraint(
        "ck_event_detections_input_index_non_negative",
        "event_detections",
        "input_index is null or input_index >= 0",
    )
    op.create_index("ix_event_detections_event_input_index", "event_detections", ["event_id", "input_index"])
    op.create_index("ix_event_detections_filter_rule_id", "event_detections", ["filter_rule_id"])
    op.alter_column("event_detections", "matched_keywords", server_default=None)
    op.alter_column("event_detections", "evidence_counts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_event_detections_filter_rule_id", table_name="event_detections")
    op.drop_index("ix_event_detections_event_input_index", table_name="event_detections")
    op.drop_constraint("ck_event_detections_input_index_non_negative", "event_detections", type_="check")
    op.drop_column("event_detections", "evidence_counts")
    op.drop_column("event_detections", "matched_keywords")
    op.drop_column("event_detections", "placeholder")
    op.drop_column("event_detections", "action")
    op.drop_column("event_detections", "detector_id")
    op.drop_column("event_detections", "filter_rule_id")
    op.drop_column("event_detections", "input_source")
    op.drop_column("event_detections", "kind")
    op.drop_column("event_detections", "input_index")
    op.drop_column("event_detections", "input_id")

    op.drop_index("ix_event_inputs_input_id", table_name="event_inputs")
    op.drop_index("ix_event_inputs_event_input_index", table_name="event_inputs")
    op.drop_index("ix_event_inputs_event_id", table_name="event_inputs")
    op.drop_table("event_inputs")

    op.drop_index("ix_analysis_events_client_request", table_name="analysis_events")
    op.drop_index("ix_analysis_events_login_created_at", table_name="analysis_events")
    op.alter_column("analysis_events", "filter_rule_set_version", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("analysis_events", "prompt_hash_key_id", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("analysis_events", "prompt_hash", existing_type=sa.String(length=160), nullable=False)
    op.drop_column("analysis_events", "filter_config_revision")
    op.drop_column("analysis_events", "client_request_id")
    op.drop_column("analysis_events", "login_id")
