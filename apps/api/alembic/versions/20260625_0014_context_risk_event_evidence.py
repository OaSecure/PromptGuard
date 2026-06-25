"""store context risk evidence on events

Revision ID: 20260625_0014
Revises: 20260624_0013
Create Date: 2026-06-25 08:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260625_0014"
down_revision = "20260624_0013"
branch_labels = None
depends_on = None


OLD_DECISION_BASIS = "decision_basis in ('no_detection', 'detection', 'content_unavailable', 'metadata_only')"
NEW_DECISION_BASIS = "decision_basis in ('no_detection', 'detection', 'content_unavailable', 'metadata_only', 'context_risk')"


def upgrade() -> None:
    op.add_column("analysis_events", sa.Column("context_risk_evidence", sa.JSON(), nullable=True))
    op.drop_constraint("ck_event_inputs_decision_basis", "event_inputs", type_="check")
    op.create_check_constraint("ck_event_inputs_decision_basis", "event_inputs", NEW_DECISION_BASIS)


def downgrade() -> None:
    op.execute("update event_inputs set decision_basis = 'no_detection' where decision_basis = 'context_risk'")
    op.drop_constraint("ck_event_inputs_decision_basis", "event_inputs", type_="check")
    op.create_check_constraint("ck_event_inputs_decision_basis", "event_inputs", OLD_DECISION_BASIS)
    op.drop_column("analysis_events", "context_risk_evidence")
