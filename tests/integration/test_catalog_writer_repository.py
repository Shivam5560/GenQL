from __future__ import annotations

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)


def test_writing_objects_is_idempotent(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    obj = DatabaseObject(
        schema_name="shop",
        object_name="customer",
        object_type=ObjectType.TABLE,
        row_estimate=100,
    )
    assert repo.write_objects([obj]) == 1
    assert repo.write_objects([obj]) == 1

    with migrated_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE schema_name = 'shop' AND object_name = 'customer'"
            )
        ).scalar_one()
    assert count == 1


def test_rewriting_an_object_updates_the_row_estimate(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    base = {
        "schema_name": "shop",
        "object_name": "orders",
        "object_type": ObjectType.TABLE,
    }
    repo.write_objects([DatabaseObject(**base, row_estimate=10)])
    repo.write_objects([DatabaseObject(**base, row_estimate=999)])

    with migrated_engine.connect() as conn:
        estimate = conn.execute(
            text(
                "SELECT row_estimate FROM genql.genql_object "
                "WHERE schema_name = 'shop' AND object_name = 'orders'"
            )
        ).scalar_one()
    assert estimate == 999


def test_writes_columns(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    column = Column(
        schema_name="shop",
        object_name="customer",
        column_name="c_state",
        ordinal=2,
        data_type="text",
        is_nullable=True,
    )
    assert repo.write_columns([column]) == 1
    assert repo.write_columns([column]) == 1
