-- The role that runs generated SQL. Idempotent: safe to run again.
-- Run as the PostgreSQL superuser, with the reader password:
--   psql -v ON_ERROR_STOP=1 -v reader_password=... -f scripts/create_reader_role.sql
--
-- Roles belong to the cluster, so this is not an Alembic migration. The migrations grant
-- it CONNECT on the database and SELECT on the analytics views, and nothing else.
-- These settings are defaults the role could change in its own session: the executor
-- sets them again inside each transaction, and the validator rejects SET (defense in depth).

SELECT 'CREATE ROLE eaa_reader LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'eaa_reader')
\gexec

ALTER ROLE eaa_reader WITH LOGIN PASSWORD :'reader_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 10;

ALTER ROLE eaa_reader SET default_transaction_read_only = on;
ALTER ROLE eaa_reader SET statement_timeout = '10s';
ALTER ROLE eaa_reader SET lock_timeout = '1s';
ALTER ROLE eaa_reader SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE eaa_reader SET search_path = analytics;
ALTER ROLE eaa_reader SET work_mem = '32MB';
ALTER ROLE eaa_reader SET temp_file_limit = '256MB';
