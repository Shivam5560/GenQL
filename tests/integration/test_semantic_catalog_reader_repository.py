"""Reads back exactly what CatalogWriter wrote — the read side that lets
graph projection run from Postgres alone."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.semantic.catalog_writer_repository import PostgresCatalogWriterRepository
from genql.repositories.semantic.semantic_catalog_reader_repository import (
    PostgresSemanticCatalogReader,
)


def test_reads_back_objects_and_constraints_a_writer_wrote(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "reader_test")
    writer = PostgresCatalogWriterRepository(migrated_engine)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="local",
                schema_name="reader_test",
                object_name="parent",
                object_type=ObjectType.TABLE,
            ),
            DatabaseObject(
                datasource_name="local",
                schema_name="reader_test",
                object_name="child",
                object_type=ObjectType.TABLE,
            ),
        ]
    )
    writer.write_constraints(
        [
            Constraint(
                datasource_name="local",
                schema_name="reader_test",
                object_name="child",
                constraint_name="child_parent_fkey",
                constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (parent_id) REFERENCES parent(id)",
                referenced_object_name="parent",
                column_names=("parent_id",),
                referenced_column_names=("id",),
            )
        ]
    )

    reader = PostgresSemanticCatalogReader(migrated_engine)
    ref = SchemaRef(datasource_name="local", schema_name="reader_test")

    objects = {o.object_name for o in reader.read_objects(ref)}
    constraints = reader.read_constraints(ref)

    assert objects == {"parent", "child"}
    assert len(constraints) == 1
    assert constraints[0].constraint_type == ConstraintType.FOREIGN_KEY
    assert constraints[0].referenced_object_name == "parent"


def test_read_objects_type_checks_against_column(migrated_engine: Engine) -> None:
    # Guards against a reader that accidentally returns Column rows: both
    # tables share several column names, and a copy-pasted SELECT is an easy
    # mistake here.
    assert Column is not DatabaseObject
