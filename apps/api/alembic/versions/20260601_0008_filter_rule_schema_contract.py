"""align filter rule schema with mvp contract

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
    op.drop_index("ix_filter_rule_versions_rule_version", table_name="filter_rule_versions")
    op.drop_table("filter_rule_versions")

    op.drop_index("ix_filter_rules_source_kind", table_name="filter_rules")
    op.drop_constraint("ck_filter_rules_source", "filter_rules", type_="check")
    op.alter_column("filter_rules", "source", new_column_name="origin", existing_type=sa.String(length=20))

    op.execute(
        """
        update filter_rules
        set origin = case
            when origin in ('built_in', 'builtin', 'built_in_detector') then 'built_in'
            when origin in ('custom', 'user', 'admin') then 'custom'
            when kind = 'detector' and detector_key is not null then 'built_in'
            when kind in ('keyword', 'regex', 'context_rule') then 'custom'
            else 'custom'
        end
        """
    )

    op.create_check_constraint(
        "ck_filter_rules_origin",
        "filter_rules",
        "origin in ('built_in', 'custom')",
    )
    op.create_index("ix_filter_rules_origin_kind", "filter_rules", ["origin", "kind"])


def downgrade() -> None:
    op.drop_index("ix_filter_rules_origin_kind", table_name="filter_rules")
    op.drop_constraint("ck_filter_rules_origin", "filter_rules", type_="check")
    op.alter_column("filter_rules", "origin", new_column_name="source", existing_type=sa.String(length=20))
    op.create_check_constraint(
        "ck_filter_rules_source",
        "filter_rules",
        "source in ('built_in', 'custom')",
    )
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
