"""Raw tables of the synthetic company in the sales schema.

The company is based in France and sells office and facility products to businesses
across Europe. Amounts are euros, numeric(12,2), excluding VAT unless the column says
otherwise. Statuses are text with CHECK constraints rather than enum types: adding a
value is then a one-line migration.

Personal data lives in customer_contacts only, on purpose: it is what the privacy layer
must keep away from generated SQL and from the LLM provider.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = """
CREATE SCHEMA sales;

CREATE TABLE sales.dataset_metadata (
    id                integer PRIMARY KEY CHECK (id = 1),
    generator_version text NOT NULL,
    seed              integer NOT NULL,
    scale             text NOT NULL,
    start_date        date NOT NULL,
    reference_date    date NOT NULL CHECK (reference_date >= start_date),
    loaded_at         timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE sales.dataset_metadata IS
    'One row: how the synthetic data was generated. reference_date is "today" for every analysis.';

CREATE TABLE sales.dataset_anomalies (
    code        text PRIMARY KEY,
    description text NOT NULL,
    entity_type text NOT NULL,
    entity_id   integer
);
COMMENT ON TABLE sales.dataset_anomalies IS
    'Anomalies injected on purpose by the generator: ground truth for the evaluation.';

CREATE TABLE sales.categories (
    id            integer PRIMARY KEY,
    category_name text NOT NULL UNIQUE
);

CREATE TABLE sales.suppliers (
    id                 integer PRIMARY KEY,
    supplier_name      text NOT NULL UNIQUE,
    country            char(2) NOT NULL,
    lead_time_days     integer NOT NULL CHECK (lead_time_days > 0)
);

CREATE TABLE sales.products (
    id           integer PRIMARY KEY,
    sku          text NOT NULL UNIQUE,
    product_name text NOT NULL,
    category_id  integer NOT NULL REFERENCES sales.categories (id),
    supplier_id  integer NOT NULL REFERENCES sales.suppliers (id),
    unit_price   numeric(12, 2) NOT NULL CHECK (unit_price > 0),
    cost_price   numeric(12, 2) NOT NULL CHECK (cost_price >= 0),
    created_at   date NOT NULL
);
COMMENT ON COLUMN sales.products.unit_price IS 'Current list price. Past prices are on order_items.';
COMMENT ON COLUMN sales.products.cost_price IS 'Current unit cost. Past costs are on order_items.';
CREATE INDEX products_category_id_idx ON sales.products (category_id);
CREATE INDEX products_supplier_id_idx ON sales.products (supplier_id);

CREATE TABLE sales.customers (
    id               integer PRIMARY KEY,
    customer_name    text NOT NULL UNIQUE,
    country          char(2) NOT NULL,
    region           text NOT NULL,
    industry         text NOT NULL,
    segment          text NOT NULL CHECK (segment IN ('SMB', 'Mid-Market', 'Enterprise')),
    payment_terms_days integer NOT NULL CHECK (payment_terms_days > 0),
    created_at       date NOT NULL
);
CREATE INDEX customers_region_idx ON sales.customers (region);

CREATE TABLE sales.customer_contacts (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES sales.customers (id),
    first_name  text NOT NULL,
    last_name   text NOT NULL,
    email       text NOT NULL,
    phone       text NOT NULL,
    job_title   text NOT NULL
);
COMMENT ON TABLE sales.customer_contacts IS
    'Personal data (synthetic). Never exposed to generated SQL or sent to the LLM provider.';
CREATE INDEX customer_contacts_customer_id_idx ON sales.customer_contacts (customer_id);

CREATE TABLE sales.orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES sales.customers (id),
    order_date  date NOT NULL,
    status      text NOT NULL CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled'))
);
CREATE INDEX orders_customer_id_idx ON sales.orders (customer_id);
CREATE INDEX orders_order_date_idx ON sales.orders (order_date);

CREATE TABLE sales.order_items (
    id              integer PRIMARY KEY,
    order_id        integer NOT NULL REFERENCES sales.orders (id),
    product_id      integer NOT NULL REFERENCES sales.products (id),
    quantity        integer NOT NULL CHECK (quantity > 0),
    unit_price      numeric(12, 2) NOT NULL CHECK (unit_price > 0),
    unit_cost       numeric(12, 2) NOT NULL CHECK (unit_cost >= 0),
    discount_amount numeric(12, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0 AND discount_amount <= quantity * unit_price),
    UNIQUE (order_id, product_id)
);
COMMENT ON COLUMN sales.order_items.unit_price IS 'List price on the order date.';
COMMENT ON COLUMN sales.order_items.unit_cost IS 'Unit cost on the order date.';
COMMENT ON COLUMN sales.order_items.discount_amount IS 'Discount on the whole line, in euros.';
CREATE INDEX order_items_product_id_idx ON sales.order_items (product_id);

CREATE TABLE sales.invoices (
    id              integer PRIMARY KEY,
    invoice_number  text NOT NULL UNIQUE,
    order_id        integer NOT NULL UNIQUE REFERENCES sales.orders (id),
    invoice_date    date NOT NULL,
    due_date        date NOT NULL CHECK (due_date >= invoice_date),
    amount_excl_vat numeric(12, 2) NOT NULL CHECK (amount_excl_vat >= 0),
    vat_rate        numeric(4, 3) NOT NULL CHECK (vat_rate >= 0 AND vat_rate < 1),
    amount_incl_vat numeric(12, 2) NOT NULL CHECK (amount_incl_vat >= amount_excl_vat),
    status          text NOT NULL CHECK (status IN ('open', 'partially_paid', 'paid'))
);
COMMENT ON COLUMN sales.invoices.status IS
    'Payment status on the reference date. Overdue is derived (due_date), not stored.';
CREATE INDEX invoices_invoice_date_idx ON sales.invoices (invoice_date);
CREATE INDEX invoices_due_date_idx ON sales.invoices (due_date);

CREATE TABLE sales.credit_notes (
    id               integer PRIMARY KEY,
    invoice_id       integer NOT NULL REFERENCES sales.invoices (id),
    credit_note_date date NOT NULL,
    amount_excl_vat  numeric(12, 2) NOT NULL CHECK (amount_excl_vat > 0),
    reason           text NOT NULL CHECK (reason IN ('return', 'pricing_error', 'goodwill'))
);
CREATE INDEX credit_notes_invoice_id_idx ON sales.credit_notes (invoice_id);

CREATE TABLE sales.payments (
    id             integer PRIMARY KEY,
    invoice_id     integer NOT NULL REFERENCES sales.invoices (id),
    payment_date   date NOT NULL,
    amount         numeric(12, 2) NOT NULL CHECK (amount > 0),
    payment_method text NOT NULL
        CHECK (payment_method IN ('bank_transfer', 'card', 'direct_debit', 'cheque'))
);
COMMENT ON COLUMN sales.payments.amount IS 'Amount received, including VAT.';
CREATE INDEX payments_invoice_id_idx ON sales.payments (invoice_id);

CREATE TABLE sales.supplier_deliveries (
    id             integer PRIMARY KEY,
    supplier_id    integer NOT NULL REFERENCES sales.suppliers (id),
    product_id     integer NOT NULL REFERENCES sales.products (id),
    quantity       integer NOT NULL CHECK (quantity > 0),
    order_date     date NOT NULL,
    expected_date  date NOT NULL CHECK (expected_date >= order_date),
    delivered_date date CHECK (delivered_date >= order_date)
);
COMMENT ON COLUMN sales.supplier_deliveries.delivered_date IS 'NULL: not delivered on the reference date.';
CREATE INDEX supplier_deliveries_supplier_id_idx ON sales.supplier_deliveries (supplier_id);
CREATE INDEX supplier_deliveries_product_id_idx ON sales.supplier_deliveries (product_id);

CREATE TABLE sales.inventory_snapshots (
    snapshot_date    date NOT NULL,
    product_id       integer NOT NULL REFERENCES sales.products (id),
    quantity_on_hand integer NOT NULL CHECK (quantity_on_hand >= 0),
    PRIMARY KEY (snapshot_date, product_id)
);
CREATE INDEX inventory_snapshots_product_id_idx ON sales.inventory_snapshots (product_id);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP SCHEMA sales CASCADE")
