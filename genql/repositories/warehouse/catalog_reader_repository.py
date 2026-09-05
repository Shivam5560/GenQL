"""Reads structural metadata from a PostgreSQL warehouse catalog."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType

_RELKIND_TO_TYPE = {
    "r": ObjectType.TABLE,
    "p": ObjectType.TABLE,
    "v": ObjectType.VIEW,
    "m": ObjectType.MATERIALIZED_VIEW,
}
_CONTYPE_TO_TYPE = {
    "p": ConstraintType.PRIMARY_KEY,
    "f": ConstraintType.FOREIGN_KEY,
    "u": ConstraintType.UNIQUE,
}

_OBJECTS_SQL = text("""
    SELECT c.relname, c.relkind, CAST(c.reltuples AS BIGINT) AS row_estimate
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY c.relname
""")

_COLUMNS_SQL = text("""
    SELECT c.relname, a.attname, a.attnum,
           format_type(a.atttypid, a.atttypmod) AS data_type,
           NOT a.attnotnull AS is_nullable,
           COALESCE(pk.is_pk, false) AS is_primary_key
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN LATERAL (
        SELECT true AS is_pk FROM pg_index i
        WHERE i.indrelid = c.oid AND i.indisprimary AND a.attnum = ANY(i.indkey)
    ) pk ON true
    WHERE n.nspname = :schema
      AND a.attnum > 0 AND NOT a.attisdropped
      AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY c.relname, a.attnum
""")

_CONSTRAINTS_SQL = text("""
    SELECT src.relname, con.conname, con.contype,
           pg_get_constraintdef(con.oid) AS definition,
           tgt.relname AS referenced_object_name
    FROM pg_constraint con
    JOIN pg_class src ON src.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = src.relnamespace
    LEFT JOIN pg_class tgt ON tgt.oid = con.confrelid
    WHERE n.nspname = :schema AND con.contype IN ('p', 'f', 'u')
    ORDER BY src.relname, con.conname
""")


class PostgresCatalogReaderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        with self._engine.connect() as conn:
            rows = conn.execute(_OBJECTS_SQL, {"schema": schema}).all()
        return [
            DatabaseObject(
                schema_name=schema,
                object_name=row.relname,
                object_type=_RELKIND_TO_TYPE[row.relkind],
                row_estimate=max(row.row_estimate, 0) if row.row_estimate is not None else None,
            )
            for row in rows
        ]

    def read_columns(self, schema: str) -> Sequence[Column]:
        with self._engine.connect() as conn:
            rows = conn.execute(_COLUMNS_SQL, {"schema": schema}).all()
        return [
            Column(
                schema_name=schema,
                object_name=row.relname,
                column_name=row.attname,
                ordinal=row.attnum,
                data_type=row.data_type,
                is_nullable=row.is_nullable,
                is_primary_key=row.is_primary_key,
            )
            for row in rows
        ]

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        with self._engine.connect() as conn:
            rows = conn.execute(_CONSTRAINTS_SQL, {"schema": schema}).all()
        return [
            Constraint(
                schema_name=schema,
                object_name=row.relname,
                constraint_name=row.conname,
                constraint_type=_CONTYPE_TO_TYPE[row.contype],
                definition=row.definition,
                referenced_object_name=row.referenced_object_name,
            )
            for row in rows
        ]
