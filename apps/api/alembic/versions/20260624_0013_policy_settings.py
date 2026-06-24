# -*- coding: utf-8 -*-
"""Add dashboard-managed policy settings.

Revision ID: 20260624_0013
Revises: 20260621_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0013"
down_revision: str | None = "20260621_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("settings_key", sa.String(length=80), nullable=False),
        sa.Column("context_classifier_action", sa.String(length=20), nullable=False),
        sa.Column("content_not_scanned_action", sa.String(length=20), nullable=False),
        sa.Column("parser_or_ocr_failure_action", sa.String(length=20), nullable=False),
        sa.Column("empty_input_action", sa.String(length=20), nullable=False),
        sa.Column("unsupported_mask_fallback_action", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("settings_key = 'default'", name="ck_policy_settings_singleton_key"),
        sa.CheckConstraint(
            "context_classifier_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_context_classifier_action",
        ),
        sa.CheckConstraint(
            "content_not_scanned_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_content_not_scanned_action",
        ),
        sa.CheckConstraint(
            "parser_or_ocr_failure_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_parser_or_ocr_failure_action",
        ),
        sa.CheckConstraint(
            "empty_input_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_empty_input_action",
        ),
        sa.CheckConstraint(
            "unsupported_mask_fallback_action in ('WARN', 'BLOCK')",
            name="ck_policy_settings_unsupported_mask_fallback_action",
        ),
        sa.CheckConstraint("version > 0", name="ck_policy_settings_version_positive"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settings_key", name="uq_policy_settings_key"),
    )
    op.create_index("ix_policy_settings_key", "policy_settings", ["settings_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_policy_settings_key", table_name="policy_settings")
    op.drop_table("policy_settings")
