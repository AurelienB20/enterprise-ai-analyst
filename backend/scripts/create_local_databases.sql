-- Creates the owner role and the two local databases. Idempotent: safe to run again.
-- Run as the PostgreSQL superuser, with the owner password from backend/.env, then
-- run create_roles.sql the same way:
--   wsl -d Debian -u postgres -- psql -v ON_ERROR_STOP=1 -v owner_password=... -f - < scripts/create_local_databases.sql
--   wsl -d Debian -u postgres -- psql -v ON_ERROR_STOP=1 -v reader_password=... -v app_password=... -f - < scripts/create_roles.sql
--
-- eaa       development database: never dropped without the owner's approval.
-- eaa_test  disposable: the database tests migrate it up and down.
-- The WSL cluster is SQL_ASCII, so the encoding is set explicitly.

SELECT 'CREATE ROLE eaa_owner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'eaa_owner')
\gexec

ALTER ROLE eaa_owner PASSWORD :'owner_password';

SELECT format(
    'CREATE DATABASE %I OWNER eaa_owner ENCODING %L TEMPLATE template0 LC_COLLATE %L LC_CTYPE %L',
    name, 'UTF8', 'C.utf8', 'C.utf8'
)
FROM unnest(ARRAY['eaa', 'eaa_test']) AS name
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = name)
\gexec

-- No role connects unless it is granted CONNECT explicitly (the reader role, milestone 0.2).
REVOKE ALL ON DATABASE eaa FROM PUBLIC;
REVOKE ALL ON DATABASE eaa_test FROM PUBLIC;

\connect eaa
REVOKE ALL ON SCHEMA public FROM PUBLIC;
\connect eaa_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
