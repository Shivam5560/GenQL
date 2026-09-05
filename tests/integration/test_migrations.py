from __future__ import annotations

from sqlalchemy import Engine, text

EXPECTED = {"genql_object", "genql_column", "genql_constraint", "genql_column_profile"}


def test_catalog_tables_exist(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'genql'")
            )
        }
    assert EXPECTED.issubset(tables)


def test_column_is_unique_per_object(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        constraint = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'genql.genql_column'::regclass AND contype = 'u'"
            )
        ).scalar_one()
    assert constraint == "uq_genql_column_identity"
