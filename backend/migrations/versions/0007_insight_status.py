"""The audit trail records how each explanation fared, not what it said.

The explanation quotes figures from the result, so its text is not stored (the audit
trail holds no result data); its status and the count of checked numbers are.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.analyses
            ADD COLUMN insight_status text
                CHECK (insight_status IN ('verified', 'fallback', 'failed')),
            ADD COLUMN insight_numbers_checked integer,
            ADD COLUMN explanation_ms double precision;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.analyses
            DROP COLUMN insight_status,
            DROP COLUMN insight_numbers_checked,
            DROP COLUMN explanation_ms;
        """
    )
