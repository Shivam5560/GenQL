"""Migration 0004 is purely additive: one new table, cascading on schema removal."""

from __future__ import annotations

from sqlalchemy import Engine, text


def test_genql_join_path_table_exists(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('genql.genql_join_path') IS NOT NULL")
        ).scalar_one()
    assert exists


def test_removing_a_schema_cascades_to_its_join_paths(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("local", "cascade_test")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_join_path "
                "(datasource_name, schema_name, source_object, target_object, path, weight) "
                "VALUES ('local', 'cascade_test', 'a', 'b', ARRAY['a', 'b'], 1.0)"
            )
        )
        conn.execute(
            text(
                "DELETE FROM genql.genql_schema "
                "WHERE datasource_name = 'local' AND schema_name = 'cascade_test'"
            )
        )
        remaining = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_join_path "
                "WHERE datasource_name = 'local' AND schema_name = 'cascade_test'"
            )
        ).scalar_one()
    assert remaining == 0
