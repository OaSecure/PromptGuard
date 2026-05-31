"""align auth user schema with mvp contract

Revision ID: 20260601_0007
Revises: 20260531_0006
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260601_0007"
down_revision: str | None = "20260531_0006"
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
        set
          login_id = 'admin',
          login_id_normalized = 'admin',
          username = 'admin',
          status = 'ACTIVE'
        where role = 'ADMIN'
          and login_id_normalized = 'admin'
        """
    )

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status in ('ACTIVE', 'DISABLED')",
    )

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
    op.create_index(
        "ix_refresh_tokens_login_expires",
        "refresh_tokens",
        ["login_id", "expires_at"],
        unique=False,
    )

    op.create_table(
        "dashboard_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("login_id", sa.String(length=80), nullable=False),
        sa.Column("session_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash", name="uq_dashboard_sessions_session_hash"),
    )
    op.create_index(
        "ix_dashboard_sessions_login_expires",
        "dashboard_sessions",
        ["login_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dashboard_sessions_login_expires", table_name="dashboard_sessions")
    op.drop_table("dashboard_sessions")

    op.drop_index("ix_refresh_tokens_login_expires", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "idle_expires_at")
    op.drop_column("refresh_tokens", "login_id")

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status in ('ACTIVE', 'PENDING', 'DISABLED')",
    )
    # email/email_normalized remain nullable because reverting them to NOT NULL can
    # fail after login_id-only users have been created.
