"""Persists catalog metadata into the semantic store.

Every write is an idempotent upsert so a rediscovery run is safe to repeat.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, TextClause, text

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject

_UPSERT_OBJECT = text("""
    INSERT INTO genql.genql_object
        (datasource_name, schema_name, object_name, object_type, row_estimate)
    VALUES (:datasource_name, :schema_name, :object_name, :object_type, :row_estimate)
    ON CONFLICT ON CONSTRAINT uq_genql_object_identity DO UPDATE
        SET object_type = EXCLUDED.object_type,
            row_estimate = EXCLUDED.row_estimate,
            discovered_at = now()
""")

_UPSERT_COLUMN = text("""
    INSERT INTO genql.genql_column
        (datasource_name, schema_name, object_name, column_name, ordinal,
         data_type, is_nullable, is_primary_key)
    VALUES (:datasource_name, :schema_name, :object_name, :column_name, :ordinal,
            :data_type, :is_nullable, :is_primary_key)
    ON CONFLICT ON CONSTRAINT uq_genql_column_identity DO UPDATE
        SET ordinal = EXCLUDED.ordinal,
            data_type = EXCLUDED.data_type,
            is_nullable = EXCLUDED.is_nullable,
            is_primary_key = EXCLUDED.is_primary_key
""")

_UPSERT_CONSTRAINT = text("""
    INSERT INTO genql.genql_constraint
        (datasource_name, schema_name, object_name, constraint_name, constraint_type,
         definition, referenced_object_name, column_names, referenced_column_names)
    VALUES (:datasource_name, :schema_name, :object_name, :constraint_name, :constraint_type,
            :definition, :referenced_object_name, :column_names, :referenced_column_names)
    ON CONFLICT ON CONSTRAINT uq_genql_constraint_identity DO UPDATE
        SET constraint_type = EXCLUDED.constraint_type,
            definition = EXCLUDED.definition,
            referenced_object_name = EXCLUDED.referenced_object_name,
            column_names = EXCLUDED.column_names,
            referenced_column_names = EXCLUDED.referenced_column_names
""")


class PostgresCatalogWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        return self._execute(_UPSERT_OBJECT, [o.model_dump(mode="json") for o in objects])

    def write_columns(self, columns: Sequence[Column]) -> int:
        return self._execute(_UPSERT_COLUMN, [c.model_dump(mode="json") for c in columns])

    def write_constraints(self, constraints: Sequence[Constraint]) -> int:
        return self._execute(_UPSERT_CONSTRAINT, [c.model_dump(mode="json") for c in constraints])

    def _execute(self, statement: TextClause, payload: list[dict[str, object]]) -> int:
        if not payload:
            return 0
        with self._engine.begin() as conn:
            conn.execute(statement, payload)
        return len(payload)
