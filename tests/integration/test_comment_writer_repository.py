"""Writes against a real table so identifier quoting is exercised for real,
not just asserted about."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.warehouse.comment_writer_repository import PostgresCommentWriter


def test_write_object_comment_lands_on_the_table(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "comment_test")
    with migrated_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS comment_test"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS comment_test.orders (id int)"))
    writer = PostgresCommentWriter(migrated_engine)
    ref = SchemaRef(datasource_name="local", schema_name="comment_test")

    writer.write_object_comment(ref, "orders", "Customer orders.")

    with migrated_engine.connect() as conn:
        comment = conn.execute(
            text("SELECT obj_description('comment_test.orders'::regclass)")
        ).scalar_one()
    assert comment == "Customer orders."
