"""Writing is an idempotent upsert, same shape as every other semantic writer."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.domain.entities.join_path import JoinPath
from genql.repositories.semantic.join_path_writer_repository import (
    PostgresJoinPathWriterRepository,
)


def test_write_persists_the_path(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "join_path_test")
    path = JoinPath(
        datasource_name="local",
        schema_name="join_path_test",
        source_object="a",
        target_object="c",
        path=("a", "b", "c"),
        weight=2.0,
    )

    written = PostgresJoinPathWriterRepository(migrated_engine).write([path])

    assert written == 1


def test_writing_the_same_path_twice_is_idempotent(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "join_path_test_2")
    path = JoinPath(
        datasource_name="local",
        schema_name="join_path_test_2",
        source_object="a",
        target_object="c",
        path=("a", "b", "c"),
        weight=2.0,
    )
    writer = PostgresJoinPathWriterRepository(migrated_engine)

    writer.write([path])
    rewritten_with_new_weight = JoinPath(**{**path.model_dump(), "weight": 5.0})
    writer.write([rewritten_with_new_weight])

    with migrated_engine.connect() as conn:
        count, weight = conn.execute(
            text(
                "SELECT count(*), max(weight) FROM genql.genql_join_path "
                "WHERE datasource_name = 'local' AND schema_name = 'join_path_test_2'"
            )
        ).one()
    assert count == 1
    assert weight == 5.0
