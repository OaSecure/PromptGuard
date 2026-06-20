"""Align event input sources with v3.5 file reference contract.

Revision ID: 20260620_0011
Revises: 20260608_0010
Create Date: 2026-06-20
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260620_0011"
down_revision: str | None = "20260608_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_SOURCE_CONSTRAINT = "source in ('composer', 'converted_paste', 'pasted_file', 'pasted_image', 'screenshot_image', 'attached_file', 'attachment_chip')"
OLD_SOURCE_CONSTRAINT = "source in ('composer', 'converted_paste', 'file', 'attachment_chip')"


def upgrade() -> None:
    op.execute("update event_inputs set source = 'attachment_chip' where source = 'file'")
    op.drop_constraint("ck_event_inputs_source", "event_inputs", type_="check")
    op.create_check_constraint("ck_event_inputs_source", "event_inputs", NEW_SOURCE_CONSTRAINT)


def downgrade() -> None:
    op.drop_constraint("ck_event_inputs_source", "event_inputs", type_="check")
    op.create_check_constraint("ck_event_inputs_source", "event_inputs", OLD_SOURCE_CONSTRAINT)
