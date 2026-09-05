#!/usr/bin/env bash
# Pagila is the Postgres port of Sakila: small, clean, fast test loop.
set -euo pipefail

DSN="${GENQL_WAREHOUSE_DSN_PSQL:-postgresql://genql:genql@localhost:5433/genql}"
BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"
TMP="$(mktemp -d)"

curl -sSfL "$BASE/pagila-schema.sql" -o "$TMP/schema.sql"
curl -sSfL "$BASE/pagila-data.sql"   -o "$TMP/data.sql"

psql "$DSN" -c 'CREATE SCHEMA IF NOT EXISTS pagila'
PGOPTIONS='--search_path=pagila' psql "$DSN" -q -f "$TMP/schema.sql"
PGOPTIONS='--search_path=pagila' psql "$DSN" -q -f "$TMP/data.sql"

echo "pagila loaded"
