"""create filter rule tables

Revision ID: 20260529_0004
Revises: 20260528_0003
Create Date: 2026-05-29
"""

from collections.abc import Sequence
import json
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260529_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILT_IN_DETECTOR_RULES = [
    {
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Email address",
        "description": "Built-in email detector metadata. Parser logic is implemented in code, not stored in DB.",
        "detector_key": "EMAIL",
        "placeholder": "EMAIL",
        "severity": "medium",
        "action": "mask",
        "editable_fields": ["enabled", "severity", "action"],
        "config_json": {},
    },
    {
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Phone number",
        "description": "Built-in phone detector metadata. Parser logic is implemented in code, not stored in DB.",
        "detector_key": "PHONE",
        "placeholder": "PHONE",
        "severity": "medium",
        "action": "mask",
        "editable_fields": ["enabled", "severity", "action"],
        "config_json": {},
    },
    {
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Resident registration number",
        "description": "Built-in RRN detector metadata. Checksum logic is implemented in code, not stored in DB.",
        "detector_key": "RRN",
        "placeholder": "RRN",
        "severity": "high",
        "action": "block",
        "editable_fields": ["enabled", "severity", "action"],
        "config_json": {},
    },
    {
        "source": "built_in",
        "kind": "detector",
        "category": "PAYMENT",
        "label": "Card number",
        "description": "Built-in card detector metadata. Luhn logic is implemented in code, not stored in DB.",
        "detector_key": "CARD",
        "placeholder": "CARD",
        "severity": "high",
        "action": "block",
        "editable_fields": ["enabled", "severity", "action"],
        "config_json": {},
    },
]


def upgrade() -> None:
    op.create_table(
        "filter_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detector_key", sa.String(length=120), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=True),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("placeholder", sa.String(length=80), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("editable_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source in ('built_in', 'custom')", name="ck_filter_rules_source"),
        sa.CheckConstraint("kind in ('detector', 'keyword', 'regex', 'context_rule')", name="ck_filter_rules_kind"),
        sa.CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_filter_rules_severity"),
        sa.CheckConstraint("action in ('allow', 'warn', 'mask', 'block')", name="ck_filter_rules_action"),
        sa.CheckConstraint("version > 0", name="ck_filter_rules_version_positive"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filter_rules_archived_at", "filter_rules", ["archived_at"])
    op.create_index("ix_filter_rules_workspace_enabled", "filter_rules", ["workspace_id", "enabled"])
    op.create_index("ix_filter_rules_workspace_source_kind", "filter_rules", ["workspace_id", "source", "kind"])

    op.create_table(
        "filter_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filter_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_filter_rule_versions_version_positive"),
        sa.CheckConstraint(
            "change_type in ('seed', 'create', 'update', 'enable', 'disable', 'archive')",
            name="ck_filter_rule_versions_change_type",
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["filter_rule_id"], ["filter_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filter_rule_versions_rule_version", "filter_rule_versions", ["filter_rule_id", "version"])
    op.create_index("ix_filter_rule_versions_workspace_created", "filter_rule_versions", ["workspace_id", "created_at"])

    connection = op.get_bind()
    for rule in BUILT_IN_DETECTOR_RULES:
        rule_id = uuid4()
        connection.execute(
            sa.text(
                """
                insert into filter_rules (
                  id, workspace_id, source, kind, category, label, description, detector_key,
                  keyword, pattern, placeholder, severity, action, enabled, editable_fields,
                  config_json, version, archived_at, created_by, updated_by
                )
                values (
                  :id, null, :source, :kind, :category, :label, :description, :detector_key,
                  null, null, :placeholder, :severity, :action, true, cast(:editable_fields as jsonb),
                  cast(:config_json as jsonb), 1, null, null, null
                )
                """
            ),
            {
                "id": rule_id,
                "source": rule["source"],
                "kind": rule["kind"],
                "category": rule["category"],
                "label": rule["label"],
                "description": rule["description"],
                "detector_key": rule["detector_key"],
                "placeholder": rule["placeholder"],
                "severity": rule["severity"],
                "action": rule["action"],
                "editable_fields": json.dumps(rule["editable_fields"]),
                "config_json": json.dumps(rule["config_json"]),
            },
        )
        connection.execute(
            sa.text(
                """
                insert into filter_rule_versions (
                  id, filter_rule_id, workspace_id, version, change_type, before_json, after_json, changed_by
                )
                values (
                  :id, :filter_rule_id, null, 1, 'seed', null, cast(:after_json as jsonb), null
                )
                """
            ),
            {
                "id": uuid4(),
                "filter_rule_id": rule_id,
                "after_json": json.dumps(
                    {
                        "source": rule["source"],
                        "kind": rule["kind"],
                        "category": rule["category"],
                        "detector_key": rule["detector_key"],
                        "editable_fields": rule["editable_fields"],
                        "config_json": rule["config_json"],
                    }
                ),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_filter_rule_versions_workspace_created", table_name="filter_rule_versions")
    op.drop_index("ix_filter_rule_versions_rule_version", table_name="filter_rule_versions")
    op.drop_table("filter_rule_versions")
    op.drop_index("ix_filter_rules_workspace_source_kind", table_name="filter_rules")
    op.drop_index("ix_filter_rules_workspace_enabled", table_name="filter_rules")
    op.drop_index("ix_filter_rules_archived_at", table_name="filter_rules")
    op.drop_table("filter_rules")
