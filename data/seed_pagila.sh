#!/usr/bin/env bash
# Pagila is the Postgres port of Sakila: small, clean, fast test loop.
#
# GENQL_SEED_EXEC selects the command used to load SQL (see below); set it
# when there is no local psql client, e.g. to run through docker exec on a
# remote VM.
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
# the dump before running it. `\b` is a GNU sed extension that BSD sed
# (macOS) silently ignores rather than rejects — it does not error, it just
# never matches, so the rewrite becomes a no-op and every object loads into
# `public` instead of `pagila`. The portable equivalent below spells the
# word boundary out with a capture group so it works on both.
sed -i.bak -E 's/([^A-Za-z0-9_]|^)public\./\1pagila./g' "$TMP/schema.sql" "$TMP/data.sql"

# The dump also grants ownership to a literal `postgres` role via
# `... OWNER TO postgres;` statements. That role does not exist on every
# cluster (this project's does not), so under -v ON_ERROR_STOP=1 the load
# aborts on the first one. Retarget ownership to whichever role runs this
# script instead of a role that may not exist.
sed -i.bak 's/OWNER TO postgres/OWNER TO CURRENT_USER/g' "$TMP/schema.sql" "$TMP/data.sql"

# The dump also installs the `vector` extension with `WITH SCHEMA public`
# (no trailing dot, so the rewrite above leaves that line alone) and then
# references its types as `public.vector`/`public.vector_cosine_ops`, which
# the blanket rewrite above does turn into `pagila.vector*` since those do
# have a dot. `pgvector`'s types live wherever the extension was installed —
# here, really `public` — never `pagila`, so put those two references back.
sed -i.bak 's/pagila\.vector/public.vector/g' "$TMP/schema.sql" "$TMP/data.sql"

# SEED_EXEC is any command that reads SQL on stdin. The default is a local
# psql; the VM has no local client, so CI and the maintainer both point it at
# the container instead:
#   SEED_EXEC='ssh genql-vm docker exec -i genql-paradedb psql -U genql -d genql_wh2 -v ON_ERROR_STOP=1'
# Word splitting on $SEED_EXEC is deliberate — it is a command line, not a path.
SEED_EXEC="${GENQL_SEED_EXEC:-psql $DSN -v ON_ERROR_STOP=1}"

echo 'CREATE SCHEMA IF NOT EXISTS pagila;' | $SEED_EXEC
$SEED_EXEC < "$TMP/schema.sql"
$SEED_EXEC < "$TMP/data.sql"

echo "pagila loaded"
