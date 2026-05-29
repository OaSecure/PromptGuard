"""switch users to login id accounts

Revision ID: 20260526_0002
Revises: 20260523_0001
Create Date: 2026-05-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_0002"
down_revision: str | None = "20260523_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("login_id", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("login_id_normalized", sa.String(length=80), nullable=True))

    op.execute(
        """
        update users
        set
          login_id = case when role = 'ADMIN' then 'ADMIN' else split_part(email, '@', 1) end,
          login_id_normalized = case when role = 'ADMIN' then 'admin' else lower(split_part(email, '@', 1)) end
        where login_id is null
        """
    )

    op.alter_column("users", "login_id", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("users", "login_id_normalized", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column("users", "email_normalized", existing_type=sa.String(length=320), nullable=True)

    op.create_unique_constraint("uq_users_login_id_normalized", "users", ["login_id_normalized"])
    op.create_index("ix_users_login_id_normalized", "users", ["login_id_normalized"])


def downgrade() -> None:
    op.drop_index("ix_users_login_id_normalized", table_name="users")
    op.drop_constraint("uq_users_login_id_normalized", "users", type_="unique")
    op.alter_column("users", "email_normalized", existing_type=sa.String(length=320), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.drop_column("users", "login_id_normalized")
    op.drop_column("users", "login_id")
