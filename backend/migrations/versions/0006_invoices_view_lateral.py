"""analytics.invoices: per-invoice LATERAL lookups instead of whole-table aggregates.

Found by the evaluation: the model wrote
    COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM analytics.invoices i
                                       WHERE i.customer_id = c.customer_id AND i.is_overdue))
which PostgreSQL runs as a correlated subquery, once per customer. The first version of
the view aggregated every payment and credit note in CTEs, so each of those runs scanned
both tables: the query hit the 5 s timeout. With LATERAL subqueries, a filter on one
customer reads only that customer's invoices, payments and credit notes, through their
indexes. Same columns, same definitions, same types.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

VIEW_V2 = """
CREATE OR REPLACE VIEW analytics.invoices AS
SELECT invoice_id, invoice_number, order_id, customer_id, invoice_date, due_date,
       amount_excl_vat, vat_rate, amount_incl_vat, credited_excl_vat, credited_incl_vat,
       paid_amount, outstanding_amount,
       outstanding_amount <= 0 AS is_settled,
       CASE WHEN outstanding_amount <= 0 THEN coalesce(last_payment_date, invoice_date) END
           AS settled_date,
       due_date < reference_date AS is_due,
       outstanding_amount > 0 AND due_date < reference_date AS is_overdue,
       CASE WHEN outstanding_amount > 0 AND due_date < reference_date
            THEN reference_date - due_date END AS days_overdue,
       CASE WHEN outstanding_amount <= 0
            THEN greatest(coalesce(last_payment_date, invoice_date) - due_date, 0) END
           AS days_paid_late
FROM (
    SELECT i.id AS invoice_id,
           i.invoice_number,
           i.order_id,
           o.customer_id,
           i.invoice_date,
           i.due_date,
           i.amount_excl_vat,
           i.vat_rate,
           i.amount_incl_vat,
           c.excl_vat AS credited_excl_vat,
           c.incl_vat AS credited_incl_vat,
           p.amount AS paid_amount,
           i.amount_incl_vat - c.incl_vat - p.amount AS outstanding_amount,
           p.last_payment_date,
           m.reference_date
    FROM sales.invoices i
    JOIN sales.orders o ON o.id = i.order_id
    CROSS JOIN sales.dataset_metadata m
    CROSS JOIN LATERAL (
        SELECT coalesce(sum(cn.amount_excl_vat), 0) AS excl_vat,
               coalesce(sum(round(cn.amount_excl_vat * (1 + i.vat_rate), 2)), 0) AS incl_vat
        FROM sales.credit_notes cn
        WHERE cn.invoice_id = i.id
    ) c
    CROSS JOIN LATERAL (
        SELECT coalesce(sum(pay.amount), 0) AS amount, max(pay.payment_date) AS last_payment_date
        FROM sales.payments pay
        WHERE pay.invoice_id = i.id
    ) p
) amounts
"""

VIEW_V1 = """
CREATE OR REPLACE VIEW analytics.invoices AS
WITH credits AS (
    SELECT cn.invoice_id,
           sum(cn.amount_excl_vat) AS excl_vat,
           sum(round(cn.amount_excl_vat * (1 + i.vat_rate), 2)) AS incl_vat
    FROM sales.credit_notes cn
    JOIN sales.invoices i ON i.id = cn.invoice_id
    GROUP BY cn.invoice_id
),
paid AS (
    SELECT invoice_id, sum(amount) AS amount, max(payment_date) AS last_payment_date
    FROM sales.payments
    GROUP BY invoice_id
),
amounts AS (
    SELECT i.id AS invoice_id, i.invoice_number, i.order_id, o.customer_id, i.invoice_date,
           i.due_date, i.amount_excl_vat, i.vat_rate, i.amount_incl_vat,
           coalesce(c.excl_vat, 0) AS credited_excl_vat,
           coalesce(c.incl_vat, 0) AS credited_incl_vat,
           coalesce(p.amount, 0) AS paid_amount,
           i.amount_incl_vat - coalesce(c.incl_vat, 0) - coalesce(p.amount, 0) AS outstanding_amount,
           p.last_payment_date, m.reference_date
    FROM sales.invoices i
    JOIN sales.orders o ON o.id = i.order_id
    CROSS JOIN sales.dataset_metadata m
    LEFT JOIN credits c ON c.invoice_id = i.id
    LEFT JOIN paid p ON p.invoice_id = i.id
)
SELECT invoice_id, invoice_number, order_id, customer_id, invoice_date, due_date,
       amount_excl_vat, vat_rate, amount_incl_vat, credited_excl_vat, credited_incl_vat,
       paid_amount, outstanding_amount,
       outstanding_amount <= 0 AS is_settled,
       CASE WHEN outstanding_amount <= 0 THEN coalesce(last_payment_date, invoice_date) END
           AS settled_date,
       due_date < reference_date AS is_due,
       outstanding_amount > 0 AND due_date < reference_date AS is_overdue,
       CASE WHEN outstanding_amount > 0 AND due_date < reference_date
            THEN reference_date - due_date END AS days_overdue,
       CASE WHEN outstanding_amount <= 0
            THEN greatest(coalesce(last_payment_date, invoice_date) - due_date, 0) END
           AS days_paid_late
FROM amounts
"""


def upgrade() -> None:
    op.execute(VIEW_V2)


def downgrade() -> None:
    op.execute(VIEW_V1)
