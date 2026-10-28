#!/usr/bin/env bash
# Start PostgreSQL, create the user + database (idempotent) and apply the schema.
set -euo pipefail
source "$(dirname "$0")/common.sh"

service postgresql start

su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"" | grep -q 1 \
  || su postgres -c "psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';\""

su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"" | grep -q 1 \
  || su postgres -c "createdb -O ${DB_USER} ${DB_NAME}"

PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -f "$REPO_DIR/database/schema.sql"
echo "Database ready: $DATABASE_URL"
