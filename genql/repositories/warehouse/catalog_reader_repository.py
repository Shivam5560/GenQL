"""Reads structural metadata from a PostgreSQL warehouse catalog."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, Row, text
from sqlalchemy.sql.elements import TextClause

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.errors import CatalogAccessError
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.warehouse.registry import CATALOG_READERS

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
           tgt.relname AS referenced_object_name,
           (
               SELECT array_agg(a.attname ORDER BY k.ord)
               FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
               JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
           ) AS column_names,
           (
               SELECT array_agg(a.attname ORDER BY k.ord)
               FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
               JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum
           ) AS referenced_column_names
    FROM pg_constraint con
    JOIN pg_class src ON src.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = src.relnamespace
    LEFT JOIN pg_class tgt ON tgt.oid = con.confrelid
    WHERE n.nspname = :schema AND con.contype IN ('p', 'f', 'u')
    ORDER BY src.relname, con.conname
""")


@CATALOG_READERS.register("postgres")
class PostgresCatalogReaderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _rows(self, statement: TextClause, ref: SchemaRef) -> Sequence[Row[Any]]:
        """Run one catalog query, translating driver failures into the domain.

        A dropped connection, a revoked SELECT on pg_class, or an unreachable
        host must reach the caller as a typed CatalogAccessError, the same way
        PostgresProfileReaderRepository raises ProfilingError: the discovery
        step catches DiscoveryError, and a raw DBAPIError would sail past it.
        """
        try:
            with self._engine.connect() as conn:
                return conn.execute(statement, {"schema": ref.schema_name}).all()
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed domain error
            raise CatalogAccessError(f"failed to read {ref.qualified_name}: {exc}") from exc

    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        rows = self._rows(_OBJECTS_SQL, ref)
        return [
            DatabaseObject(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                object_name=row.relname,
                object_type=_RELKIND_TO_TYPE[row.relkind],
                row_estimate=(
                    row.row_estimate
                    if row.row_estimate is not None and row.row_estimate >= 0
                    else None
                ),
            )
            for row in rows
        ]

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        rows = self._rows(_COLUMNS_SQL, ref)
        return [
            Column(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                object_name=row.relname,
                column_name=row.attname,
                ordinal=row.attnum,
                data_type=row.data_type,
                is_nullable=row.is_nullable,
                is_primary_key=row.is_primary_key,
            )
            for row in rows
        ]

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        rows = self._rows(_CONSTRAINTS_SQL, ref)
        return [
            Constraint(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                object_name=row.relname,
                constraint_name=row.conname,
                constraint_type=_CONTYPE_TO_TYPE[row.contype],
                definition=row.definition,
                referenced_object_name=row.referenced_object_name,
                column_names=tuple(row.column_names or ()),
                referenced_column_names=tuple(row.referenced_column_names or ()),
            )
            for row in rows
        ]
