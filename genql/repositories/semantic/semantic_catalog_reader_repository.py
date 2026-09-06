"""Reads structural metadata back out of the semantic store, by SchemaRef."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef

_SELECT_OBJECTS = text("""
    SELECT datasource_name, schema_name, object_name, object_type, row_estimate
    FROM genql.genql_object
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_SELECT_CONSTRAINTS = text("""
    SELECT datasource_name, schema_name, object_name, constraint_name, constraint_type,
           definition, referenced_object_name, column_names, referenced_column_names
    FROM genql.genql_constraint
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")


class PostgresSemanticCatalogReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_OBJECTS, ref.model_dump()).all()
        return [DatabaseObject.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_CONSTRAINTS, ref.model_dump()).all()
        return [Constraint.model_validate(r._mapping) for r in rows]  # noqa: SLF001
