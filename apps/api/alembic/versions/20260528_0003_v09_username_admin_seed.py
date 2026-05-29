"""align users with v0.10 account metadata and admin seed

Revision ID: 20260528_0003
Revises: 20260526_0002
Create Date: 2026-05-28
"""

from collections.abc import Sequence
import os
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from argon2 import PasswordHasher

revision: str = "20260528_0003"
down_revision: str | None = "20260526_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ADMIN_LOGIN_ID = "admin"
INITIAL_ADMIN_PASSWORD_ENV = "PROMPTGUARD_INITIAL_ADMIN_PASSWORD"
DEFAULT_INITIAL_ADMIN_PASSWORD = "Admin1234!ChangeMe"


def get_initial_admin_password() -> str:
    return os.getenv(INITIAL_ADMIN_PASSWORD_ENV, DEFAULT_INITIAL_ADMIN_PASSWORD)


def hash_initial_admin_password(initial_password: str | None = None) -> str:
    return PasswordHasher().hash(initial_password or get_initial_admin_password())


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("department", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        update users
        set
          username = case
            when role = 'ADMIN' and login_id_normalized = 'admin' then 'admin'
            else coalesce(username, login_id, split_part(email, '@', 1))
          end
        where username is null
        """
    )

    connection = op.get_bind()
    admin_exists = connection.execute(
        sa.text("select 1 from users where login_id_normalized = :login_id or role = 'ADMIN' limit 1"),
        {"login_id": DEFAULT_ADMIN_LOGIN_ID},
    ).first()

    if admin_exists is None:
        admin_id = uuid4()
        admin_password_hash = hash_initial_admin_password()
        connection.execute(
            sa.text(
                """
                insert into users (
                  id,
                  login_id,
                  login_id_normalized,
                  username,
                  email,
                  email_normalized,
                  department,
                  display_name,
                  role,
                  status,
                  password_hash,
                  password_hash_algorithm,
                  password_hash_params
                )
                values (
                  :id,
                  :login_id,
                  :login_id_normalized,
                  :username,
                  null,
                  null,
                  null,
                  'PromptGuard Admin',
                  'ADMIN',
                  'ACTIVE',
                  :password_hash,
                  'argon2id',
                  null
                )
                """
            ),
            {
                "id": admin_id,
                "login_id": DEFAULT_ADMIN_LOGIN_ID,
                "login_id_normalized": DEFAULT_ADMIN_LOGIN_ID,
                "username": DEFAULT_ADMIN_LOGIN_ID,
                "password_hash": admin_password_hash,
            },
        )

    op.alter_column("users", "username", existing_type=sa.String(length=80), nullable=False)


def downgrade() -> None:
    op.drop_column("users", "last_event_at")
    op.drop_column("users", "department")
    op.drop_column("users", "username")
