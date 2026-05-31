"""add unified filter rule tables

Revision ID: 20260530_0005
Revises: 20260530_0004
Create Date: 2026-05-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260530_0005"
down_revision: str | None = "20260530_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BUILT_IN_RULES = [
    {
        "id": "00000000-0000-4000-8000-000000000101",
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Email Address",
        "description": "Detects email address patterns.",
        "detector_key": "EMAIL",
        "placeholder": "EMAIL",
        "severity": "medium",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {"severity": True, "action": True, "enabled": True},
        "version": 1,
    },
    {
        "id": "00000000-0000-4000-8000-000000000102",
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Phone Number",
        "description": "Detects Korean phone number patterns.",
        "detector_key": "PHONE",
        "placeholder": "PHONE",
        "severity": "medium",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {"severity": True, "action": True, "enabled": True},
        "version": 1,
    },
    {
        "id": "00000000-0000-4000-8000-000000000103",
        "source": "built_in",
        "kind": "detector",
        "category": "PII",
        "label": "Resident Registration Number",
        "description": "Detects valid dummy resident registration numbers.",
        "detector_key": "RRN",
        "placeholder": "RRN",
        "severity": "high",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {"severity": True, "action": True, "enabled": True},
        "version": 1,
    },
    {
        "id": "00000000-0000-4000-8000-000000000104",
        "source": "built_in",
        "kind": "detector",
        "category": "Payment",
        "label": "Card Number",
        "description": "Detects Luhn-valid card numbers.",
        "detector_key": "CARD",
        "placeholder": "CARD",
        "severity": "high",
        "action": "MASK",
        "enabled": True,
        "editable_fields": {"severity": True, "action": True, "enabled": True},
        "version": 1,
    },
]


def upgrade() -> None:
    op.create_table(
        "filter_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detector_key", sa.String(length=80), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("placeholder", sa.String(length=80), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("editable_fields", sa.JSON(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source in ('built_in', 'custom')", name="ck_filter_rules_source"),
        sa.CheckConstraint("kind in ('detector', 'keyword', 'regex', 'context_rule')", name="ck_filter_rules_kind"),
        sa.CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_filter_rules_severity",
        ),
        sa.CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_filter_rules_action"),
        sa.CheckConstraint("version > 0", name="ck_filter_rules_version_positive"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("detector_key", name="uq_filter_rules_detector_key"),
    )
    op.create_index("ix_filter_rules_archived_at", "filter_rules", ["archived_at"])
    op.create_index("ix_filter_rules_enabled", "filter_rules", ["enabled"])
    op.create_index("ix_filter_rules_source_kind", "filter_rules", ["source", "kind"])

    op.create_table(
        "filter_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filter_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_filter_rule_versions_version_positive"),
        sa.CheckConstraint(
            "change_type in ('create', 'update', 'enable', 'disable', 'archive')",
            name="ck_filter_rule_versions_change_type",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["filter_rule_id"], ["filter_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filter_rule_versions_rule_version", "filter_rule_versions", ["filter_rule_id", "version"])

    filter_rules_table = sa.table(
        "filter_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("source", sa.String),
        sa.column("kind", sa.String),
        sa.column("category", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("detector_key", sa.String),
        sa.column("placeholder", sa.String),
        sa.column("severity", sa.String),
        sa.column("action", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("editable_fields", sa.JSON),
        sa.column("version", sa.Integer),
    )
    op.bulk_insert(filter_rules_table, BUILT_IN_RULES)


def downgrade() -> None:
    op.drop_index("ix_filter_rule_versions_rule_version", table_name="filter_rule_versions")
    op.drop_table("filter_rule_versions")
    op.drop_index("ix_filter_rules_source_kind", table_name="filter_rules")
    op.drop_index("ix_filter_rules_enabled", table_name="filter_rules")
    op.drop_index("ix_filter_rules_archived_at", table_name="filter_rules")
    op.drop_table("filter_rules")
