#!/bin/sh
# Run by the postgres image on an empty volume only. Creates the owner role (migrations,
# data loading), gives it the database, then the reader and app roles
# (backend/scripts/create_roles.sql). Passwords come from the environment.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v owner_password="$EAA_OWNER_PASSWORD" <<'SQL'
CREATE ROLE eaa_owner LOGIN PASSWORD :'owner_password';
ALTER DATABASE eaa OWNER TO eaa_owner;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v reader_password="$EAA_READER_PASSWORD" -v app_password="$EAA_APP_PASSWORD" \
    -f /eaa/create_roles.sql
