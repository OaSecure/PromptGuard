"""Replace exact event input size with a coarse privacy bucket.

Revision ID: 20260621_0012
Revises: 20260620_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_0012"
down_revision: str | None = "20260620_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUCKET_CASE_SQL = """case
when size_bytes = 0 then 'empty'
when size_bytes <= 1048576 then 'small'
when size_bytes <= 10485760 then 'medium'
else 'large' end"""
NEW_KIND_CONSTRAINT = "kind in ('text', 'file_reference', 'attachment_metadata', 'unsupported_attachment')"


def upgrade() -> None:
    op.add_column("event_inputs", sa.Column("size_bucket", sa.String(length=20), nullable=True))
    op.execute(f"update event_inputs set size_bucket = {BUCKET_CASE_SQL}")
    op.alter_column("event_inputs", "size_bucket", existing_type=sa.String(length=20), nullable=False)
    op.drop_constraint("ck_event_inputs_size_bytes_non_negative", "event_inputs", type_="check")
    op.drop_column("event_inputs", "size_bytes")
    op.drop_constraint("ck_event_inputs_kind", "event_inputs", type_="check")
    op.create_check_constraint("ck_event_inputs_kind", "event_inputs", NEW_KIND_CONSTRAINT)
    op.create_check_constraint(
        "ck_event_inputs_size_bucket",
        "event_inputs",
        "size_bucket in ('empty', 'small', 'medium', 'large')",
    )


def downgrade() -> None:
    raise RuntimeError("20260621_0012 is intentionally irreversible: exact size_bytes were deleted for privacy")
