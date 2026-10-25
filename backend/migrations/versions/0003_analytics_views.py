"""The analytics schema: semantic views, the only objects generated SQL may read.

The views encode the business definitions (src/eaa/semantic/model.toml documents every
column and metric; tests check that both agree). They run with their owner's rights, so
eaa_reader reads them without any privilege on the sales tables, and personal data
(sales.customer_contacts) is in none of them.

Every relative period uses the dataset's reference date, never CURRENT_DATE.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE SCHEMA analytics;
COMMENT ON SCHEMA analytics IS 'Semantic views: what generated SQL may read.';

CREATE VIEW analytics.dataset_info AS
SELECT reference_date, start_date
FROM sales.dataset_metadata;

CREATE VIEW analytics.customers AS
SELECT id AS customer_id, customer_name, country, region, industry, segment,
       payment_terms_days, created_at
FROM sales.customers;

CREATE VIEW analytics.suppliers AS
SELECT id AS supplier_id, supplier_name, country, lead_time_days
FROM sales.suppliers;

CREATE VIEW analytics.products AS
SELECT p.id AS product_id, p.sku, p.product_name, c.category_name, p.supplier_id,
       s.supplier_name, p.unit_price AS current_unit_price, p.cost_price AS current_unit_cost
FROM sales.products p
JOIN sales.categories c ON c.id = p.category_id
JOIN sales.suppliers s ON s.id = p.supplier_id;

-- One row per line of an invoiced order (shipped or delivered): the grain of revenue.
-- Pending orders are not invoiced yet and cancelled orders never are, so neither is here.
-- Credit notes are deducted from the line they credit, in the invoice's period.
CREATE VIEW analytics.sales_lines AS
WITH credited AS (
    SELECT invoice_id, product_id, sum(amount_excl_vat) AS amount
    FROM sales.credit_notes
    GROUP BY invoice_id, product_id
)
SELECT oi.id AS line_id,
       o.id AS order_id,
       i.id AS invoice_id,
       o.customer_id,
       cu.region AS customer_region,
       cu.country AS customer_country,
       cu.segment AS customer_segment,
       cu.industry AS customer_industry,
       oi.product_id,
       cat.category_name,
       p.supplier_id,
       o.order_date,
       i.invoice_date,
       oi.quantity,
       oi.unit_price,
       oi.quantity * oi.unit_price AS gross_amount,
       oi.discount_amount,
       coalesce(cr.amount, 0) AS credited_amount,
       oi.quantity * oi.unit_price - oi.discount_amount - coalesce(cr.amount, 0) AS net_revenue,
       oi.quantity * oi.unit_cost AS cogs,
       oi.quantity * oi.unit_price - oi.discount_amount - coalesce(cr.amount, 0)
           - oi.quantity * oi.unit_cost AS gross_margin
FROM sales.order_items oi
JOIN sales.orders o ON o.id = oi.order_id
JOIN sales.invoices i ON i.order_id = o.id
JOIN sales.customers cu ON cu.id = o.customer_id
JOIN sales.products p ON p.id = oi.product_id
JOIN sales.categories cat ON cat.id = p.category_id
LEFT JOIN credited cr ON cr.invoice_id = i.id AND cr.product_id = oi.product_id;

-- Every order, whatever its status: for counts, cancellations and the order pipeline.
CREATE VIEW analytics.orders AS
SELECT o.id AS order_id,
       o.customer_id,
       o.order_date,
       o.status,
       i.id IS NOT NULL AS is_invoiced,
       i.invoice_date,
       count(oi.id) AS line_count,
       sum(oi.quantity * oi.unit_price - oi.discount_amount) AS ordered_amount
FROM sales.orders o
JOIN sales.order_items oi ON oi.order_id = o.id
LEFT JOIN sales.invoices i ON i.order_id = o.id
GROUP BY o.id, i.id;

-- Invoices with what was credited, paid and is still owed on the reference date.
CREATE VIEW analytics.invoices AS
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
    SELECT i.id AS invoice_id,
           i.invoice_number,
           i.order_id,
           o.customer_id,
           i.invoice_date,
           i.due_date,
           i.amount_excl_vat,
           i.vat_rate,
           i.amount_incl_vat,
           coalesce(c.excl_vat, 0) AS credited_excl_vat,
           coalesce(c.incl_vat, 0) AS credited_incl_vat,
           coalesce(p.amount, 0) AS paid_amount,
           i.amount_incl_vat - coalesce(c.incl_vat, 0) - coalesce(p.amount, 0) AS outstanding_amount,
           p.last_payment_date,
           m.reference_date
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
FROM amounts;

-- One row per customer: activity and revenue windows on the reference date.
CREATE VIEW analytics.customer_activity AS
WITH orders AS (
    SELECT customer_id,
           max(order_date) AS last_order_date,
           count(*) AS order_count
    FROM sales.orders
    WHERE status <> 'cancelled'
    GROUP BY customer_id
),
recent AS (
    SELECT o.customer_id,
           bool_or(o.order_date > m.reference_date - 90) AS ordered_last_90_days,
           bool_or(o.order_date > m.reference_date - 180
                   AND o.order_date <= m.reference_date - 90) AS ordered_previous_90_days
    FROM sales.orders o
    CROSS JOIN sales.dataset_metadata m
    WHERE o.status <> 'cancelled'
    GROUP BY o.customer_id
),
revenue AS (
    SELECT sl.customer_id,
           sum(sl.net_revenue) FILTER (WHERE sl.invoice_date > m.reference_date - 365)
               AS net_revenue_last_12_months,
           sum(sl.net_revenue) FILTER (WHERE sl.invoice_date > m.reference_date - 730
                                         AND sl.invoice_date <= m.reference_date - 365)
               AS net_revenue_previous_12_months
    FROM analytics.sales_lines sl
    CROSS JOIN sales.dataset_metadata m
    GROUP BY sl.customer_id
)
SELECT c.id AS customer_id,
       o.last_order_date,
       m.reference_date - o.last_order_date AS days_since_last_order,
       coalesce(o.order_count, 0) AS order_count,
       coalesce(r.ordered_last_90_days, false) AS is_active,
       coalesce(r.ordered_previous_90_days, false)
           AND NOT coalesce(r.ordered_last_90_days, false) AS became_inactive,
       coalesce(v.net_revenue_last_12_months, 0) AS net_revenue_last_12_months,
       coalesce(v.net_revenue_previous_12_months, 0) AS net_revenue_previous_12_months
FROM sales.customers c
CROSS JOIN sales.dataset_metadata m
LEFT JOIN orders o ON o.customer_id = c.id
LEFT JOIN recent r ON r.customer_id = c.id
LEFT JOIN revenue v ON v.customer_id = c.id;

-- Supplier deliveries; late means delivered after the expected date, or still missing
-- once the expected date has passed.
CREATE VIEW analytics.supplier_deliveries AS
SELECT d.id AS delivery_id,
       d.supplier_id,
       s.supplier_name,
       d.product_id,
       d.quantity,
       d.order_date,
       d.expected_date,
       d.delivered_date,
       d.delivered_date IS NOT NULL AS is_delivered,
       d.expected_date < m.reference_date AS is_due,
       coalesce(d.delivered_date > d.expected_date,
                d.expected_date < m.reference_date) AS is_late,
       greatest(coalesce(d.delivered_date, m.reference_date) - d.expected_date, 0) AS days_late
FROM sales.supplier_deliveries d
JOIN sales.suppliers s ON s.id = d.supplier_id
CROSS JOIN sales.dataset_metadata m;

CREATE VIEW analytics.inventory_snapshots AS
SELECT snapshot_date, product_id, quantity_on_hand
FROM sales.inventory_snapshots;

-- Nothing by default: PUBLIC loses CONNECT and TEMP on the database and every right on
-- the public schema, then eaa_reader gets exactly CONNECT and SELECT on these views.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO eaa_reader', current_database());
END
$$;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA analytics TO eaa_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO eaa_reader;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    # PUBLIC's rights are not given back: a downgrade must not loosen permissions.
    op.execute(
        """
        DROP SCHEMA analytics CASCADE;
        DO $$
        BEGIN
            EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM eaa_reader', current_database());
        END
        $$;
        """
    )
