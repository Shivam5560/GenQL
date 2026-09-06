"""read-only execution role

Revision ID: 0006
Revises: 0005

Creates the login role guarded execution connects as. `pg_read_all_data`
(PostgreSQL 14+) is granted rather than a per-schema `GRANT SELECT` plus
`ALTER DEFAULT PRIVILEGES`: the predefined role confers SELECT on every table
and USAGE on every schema, including ones created after this migration ran,
which removes the "a newly-added schema silently has no grant" failure mode
instead of merely narrowing it. No write privilege of any kind is granted, so
the role stays read-only by construction.

The password comes from GENQL_READONLY_DB_PASSWORD and is never hardcoded.
DDL cannot be parameterized, so the value is validated against a strict
character class before it is interpolated — a password that would need
escaping is rejected rather than escaped.
"""

from __future__ import annotations

import re

from alembic import op
from sqlalchemy import text

from genql.core.settings import Settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ROLE = "genql_readonly"
_SAFE_PASSWORD = re.compile(r"^[A-Za-z0-9_.:@+~-]{8,128}$")


def _password() -> str:
    password = Settings().readonly_db_password.strip()
    if not password:
        raise RuntimeError(
            "GENQL_READONLY_DB_PASSWORD is unset. Migration 0006 provisions the "
            f"{ROLE!r} login role and refuses to invent a password for it."
        )
    if not _SAFE_PASSWORD.match(password):
        raise RuntimeError(
            "GENQL_READONLY_DB_PASSWORD must be 8-128 characters from "
            "[A-Za-z0-9_.:@+~-]; DDL cannot be parameterized and this "
            "migration rejects rather than escapes."
        )
    return password


def upgrade() -> None:
    password = _password()
    database = op.get_bind().execute(text("SELECT current_database()")).scalar_one()
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                EXECUTE 'CREATE ROLE {ROLE} LOGIN PASSWORD ''{password}''';
            ELSE
                EXECUTE 'ALTER ROLE {ROLE} LOGIN PASSWORD ''{password}''';
            END IF;
        END $$;
    """)
    op.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {ROLE}')
    op.execute(f"GRANT pg_read_all_data TO {ROLE}")


def downgrade() -> None:
    database = op.get_bind().execute(text("SELECT current_database()")).scalar_one()
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                EXECUTE 'REVOKE pg_read_all_data FROM {ROLE}';
                EXECUTE 'REVOKE CONNECT ON DATABASE "{database}" FROM {ROLE}';
                EXECUTE 'DROP OWNED BY {ROLE}';
                EXECUTE 'DROP ROLE {ROLE}';
            END IF;
        END $$;
    """)
