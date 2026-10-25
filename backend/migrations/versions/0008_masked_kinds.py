"""The audit trail records which kinds of personal data were masked in each question.

The kinds only ("EMAIL", "PHONE"), never the values: enough to count privacy events in
the service metrics.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app.analyses ADD COLUMN masked_personal_data text[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app.analyses DROP COLUMN masked_personal_data")
