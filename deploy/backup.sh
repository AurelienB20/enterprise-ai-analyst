#!/bin/sh
# Back up the database (custom format) into deploy/backups/, from this directory:
#   ./backup.sh
# The sales data is synthetic and can be regenerated; what matters is the audit trail
# (schema app). The whole database is dumped anyway: restoring is then one command.
set -eu

mkdir -p backups
file="backups/eaa-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U postgres -d eaa --format=custom > "$file"
echo "Backup written to $file ($(du -h "$file" | cut -f1))"
echo "Restore into a NEW database (never over eaa without a reason):"
echo "  docker compose exec -T db createdb -U postgres -O eaa_owner eaa_restored"
echo "  docker compose exec -T db pg_restore -U postgres -d eaa_restored < $file"
