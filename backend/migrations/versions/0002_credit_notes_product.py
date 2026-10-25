"""Credit notes name the product they credit.

Without it, a credit could only be spread over the invoice's lines pro rata, which
blurs product-level questions ("which product had a returns spike?"). The column is
NOT NULL: load the dataset after this migration (generator version 2).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE sales.credit_notes
            ADD COLUMN product_id integer NOT NULL REFERENCES sales.products (id);
        CREATE INDEX credit_notes_product_id_idx ON sales.credit_notes (product_id);
        COMMENT ON COLUMN sales.credit_notes.product_id IS
            'The product whose invoice line this note credits.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.credit_notes DROP COLUMN product_id")
