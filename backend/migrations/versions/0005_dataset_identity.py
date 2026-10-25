"""dataset_info also says which dataset is loaded (generator version, seed, scale).

The evaluation records it with every report: a score means nothing without the data it
was measured on.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.dataset_info AS
        SELECT reference_date, start_date, generator_version, seed, scale
        FROM sales.dataset_metadata
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW analytics.dataset_info;
        CREATE VIEW analytics.dataset_info AS
        SELECT reference_date, start_date FROM sales.dataset_metadata;
        GRANT SELECT ON analytics.dataset_info TO eaa_reader;
        """
    )
