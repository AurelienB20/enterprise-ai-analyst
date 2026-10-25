"""The app schema: the audit trail of every analysis.

One row per question: what was asked, every SQL the model proposed and why it was
accepted or rejected, the SQL that ran, timings, tokens and cost. Never the result rows:
the audit trail must not become a copy of the business data.

The question itself is stored as typed by the user, who may write personal data in it;
its retention is a decision for the privacy milestone (docs/privacy.md, 0.6).

eaa_app, the API's role, may insert and read here, and nothing else.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE SCHEMA app;
COMMENT ON SCHEMA app IS 'Application data: the audit trail. Never readable by eaa_reader.';

CREATE TABLE app.analyses (
    id                uuid PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    correlation_id    text,
    question          text NOT NULL,
    status            text NOT NULL CHECK (status IN ('answered', 'declined', 'rejected', 'failed')),
    model             text,
    attempts          jsonb NOT NULL DEFAULT '[]',
    executed_sql      text,
    views             text[] NOT NULL DEFAULT '{}',
    row_count         integer,
    truncated         boolean,
    assumptions       jsonb NOT NULL DEFAULT '[]',
    ambiguities       jsonb NOT NULL DEFAULT '[]',
    explanation       text,
    error_kind        text,
    error_message     text,
    generation_ms     double precision,
    execution_ms      double precision,
    total_ms          double precision NOT NULL,
    input_tokens      integer NOT NULL DEFAULT 0,
    output_tokens     integer NOT NULL DEFAULT 0,
    cache_read_tokens integer NOT NULL DEFAULT 0,
    cost_usd          numeric(10, 6) NOT NULL DEFAULT 0
);
COMMENT ON COLUMN app.analyses.attempts IS
    'Every SQL proposal: {"sql", "outcome", "message"}. outcome: accepted, rejected, failed.';
CREATE INDEX analyses_created_at_idx ON app.analyses (created_at);

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO eaa_app', current_database());
END
$$;
GRANT USAGE ON SCHEMA app TO eaa_app;
GRANT SELECT, INSERT ON app.analyses TO eaa_app;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(
        """
        DROP SCHEMA app CASCADE;
        DO $$
        BEGIN
            EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM eaa_app', current_database());
        END
        $$;
        """
    )
