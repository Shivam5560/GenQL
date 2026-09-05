#!/usr/bin/env bash
# Pagila is the Postgres port of Sakila: small, clean, fast test loop.
#
# UNVERIFIED: this script has never been executed (no local psql client in
# this environment — see data/README.md). It is believed correct by
# construction; TPC-DS is the verified primary fixture.
set -euo pipefail

DSN="${GENQL_WAREHOUSE_DSN_PSQL:-postgresql://genql:genql@localhost:5433/genql}"
BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"
TMP="$(mktemp -d)"

curl -sSfL "$BASE/pagila-schema.sql" -o "$TMP/schema.sql"
curl -sSfL "$BASE/pagila-data.sql"   -o "$TMP/data.sql"

# pagila-schema.sql / pagila-data.sql are pg_dump-shaped: the current dump
# (verified 2026-09-05, github.com/devrimgunduz/pagila) opens with
# `SELECT pg_catalog.set_config('search_path', '', false);` and then
# schema-qualifies every single object as `public.<name>` (CREATE TABLE
# public.actor, INSERT INTO public.actor, ...). Setting PGOPTIONS alone does
# nothing here: search_path is irrelevant when every statement already names
# its schema explicitly, and that schema is always `public`, never `pagila`.
# Rewrite the `public.` qualifier (word-bounded, dot-terminated, so it only
# matches the schema qualifier and not e.g. `ALTER SCHEMA public OWNER ...`
# or comment lines reading "Schema: public") to `pagila.` in our own copy of
# the dump before running it.
sed -i.bak 's/\bpublic\./pagila./g' "$TMP/schema.sql" "$TMP/data.sql"

# -v ON_ERROR_STOP=1 makes a failing statement abort the script (and this
# psql's own exit code) instead of psql reporting the error per-statement and
# still exiting 0 — `set -euo pipefail` alone does not catch that.
psql "$DSN" -v ON_ERROR_STOP=1 -c 'CREATE SCHEMA IF NOT EXISTS pagila'
PGOPTIONS='--search_path=pagila' psql "$DSN" -v ON_ERROR_STOP=1 -q -f "$TMP/schema.sql"
PGOPTIONS='--search_path=pagila' psql "$DSN" -v ON_ERROR_STOP=1 -q -f "$TMP/data.sql"

echo "pagila loaded"
