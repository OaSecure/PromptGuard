"""align auth user schema with MVP contract

Revision ID: 20260601_0007
Revises: 20260601_0006
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260601_0007"
down_revision: str | None = "20260601_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        update users
        set status = 'DISABLED'
        where status not in ('ACTIVE', 'DISABLED')
          and role != 'ADMIN'
        """
    )
    op.execute(
        """
        update users
        set status = 'ACTIVE',
            login_id = 'admin',
            login_id_normalized = 'admin',
            username = 'admin'
        where role = 'ADMIN'
          and login_id_normalized = 'admin'
        """
    )
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.create_check_constraint("ck_users_status", "users", "status in ('ACTIVE', 'DISABLED')")

    op.add_column("refresh_tokens", sa.Column("login_id", sa.String(length=80), nullable=True))
    op.add_column("refresh_tokens", sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        update refresh_tokens
        set login_id = users.login_id
        from users
        where refresh_tokens.user_id = users.id
          and refresh_tokens.login_id is null
        """
    )
    op.alter_column("refresh_tokens", "login_id", existing_type=sa.String(length=80), nullable=False)
    op.create_index("ix_refresh_tokens_login_expires", "refresh_tokens", ["login_id", "expires_at"])

    op.add_column("dashboard_sessions", sa.Column("login_id", sa.String(length=80), nullable=True))
    op.execute(
        """
        update dashboard_sessions
        set login_id = users.login_id
        from users
        where dashboard_sessions.user_id = users.id
          and dashboard_sessions.login_id is null
        """
    )
    op.execute("delete from dashboard_sessions where login_id is null")
    op.alter_column("dashboard_sessions", "login_id", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("dashboard_sessions", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_index("ix_dashboard_sessions_login_expires", "dashboard_sessions", ["login_id", "expires_at"])

    op.drop_table("registration_settings")
    op.drop_index("ix_invites_created_by_user_id", table_name="invites")
    op.drop_table("invites")


def downgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role in ('ADMIN', 'USER')", name="ck_invites_role"),
        sa.CheckConstraint("max_uses > 0", name="ck_invites_max_uses_positive"),
        sa.CheckConstraint("use_count >= 0", name="ck_invites_use_count_non_negative"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_invites_code_hash"),
    )
    op.create_index("ix_invites_created_by_user_id", "invites", ["created_by_user_id"])
    op.create_table(
        "registration_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("workspace_code_hash", sa.String(length=128), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_registration_settings_singleton"),
        sa.CheckConstraint(
            "mode in ('INVITE_ONLY', 'WORKSPACE_CODE', 'OPEN_SIGNUP')",
            name="ck_registration_settings_mode",
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("insert into registration_settings (id, mode) values (1, 'INVITE_ONLY')")

    op.drop_index("ix_dashboard_sessions_login_expires", table_name="dashboard_sessions")
    op.alter_column("dashboard_sessions", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column("dashboard_sessions", "login_id")

    op.drop_index("ix_refresh_tokens_login_expires", table_name="refresh_tokens")
    op.alter_column("refresh_tokens", "login_id", existing_type=sa.String(length=80), nullable=True)
    op.drop_column("refresh_tokens", "idle_expires_at")
    op.drop_column("refresh_tokens", "login_id")

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.create_check_constraint("ck_users_status", "users", "status in ('ACTIVE', 'PENDING', 'DISABLED')")
