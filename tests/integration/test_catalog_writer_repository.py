from __future__ import annotations

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
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

    with migrated_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_column "
                "WHERE schema_name = 'shop' AND object_name = 'customer' "
                "AND column_name = 'c_state'"
            )
        ).scalar_one()
    assert count == 1


def test_writes_constraint_column_names_and_referenced_column_names(
    migrated_engine: Engine,
) -> None:
    """Migration 0002 adds column_names/referenced_column_names; this proves
    both a real FK's constrained columns and its referenced columns survive a
    round trip through the writer. See final-review.md I5.
    """
    repo = PostgresCatalogWriterRepository(migrated_engine)
    fk = Constraint(
        schema_name="shop",
        object_name="orders",
        constraint_name="orders_customer_fk",
        constraint_type=ConstraintType.FOREIGN_KEY,
        definition="FOREIGN KEY (o_customer_sk) REFERENCES shop.customer(c_customer_sk)",
        referenced_object_name="customer",
        column_names=("o_customer_sk",),
        referenced_column_names=("c_customer_sk",),
    )
    assert repo.write_constraints([fk]) == 1

    with migrated_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT column_names, referenced_column_names FROM genql.genql_constraint "
                "WHERE schema_name = 'shop' AND object_name = 'orders' "
                "AND constraint_name = 'orders_customer_fk'"
            )
        ).one()
    assert row.column_names == ["o_customer_sk"]
    assert row.referenced_column_names == ["c_customer_sk"]
