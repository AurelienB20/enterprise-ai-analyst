-- The two least-privilege roles of the application. Idempotent: safe to run again.
-- Run as the PostgreSQL superuser, with both passwords:
--   psql -v ON_ERROR_STOP=1 -v reader_password=... -v app_password=... -f scripts/create_roles.sql
--
-- eaa_reader  runs generated SQL: SELECT on the analytics views only.
-- eaa_app     the API's own role: writes and reads the audit trail (schema app) only.
--             It cannot read the analytics views or the raw tables.
--
-- Roles belong to the cluster, so this is not an Alembic migration; the migrations grant
-- the rights inside the database. The settings below are defaults the role could change
-- in its own session: the executor sets them again inside each transaction, and the
-- validator rejects SET (defense in depth).

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

SELECT 'CREATE ROLE eaa_app LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'eaa_app')
\gexec

ALTER ROLE eaa_app WITH LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 20;

ALTER ROLE eaa_app SET statement_timeout = '5s';
ALTER ROLE eaa_app SET lock_timeout = '1s';
ALTER ROLE eaa_app SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE eaa_app SET search_path = app;
