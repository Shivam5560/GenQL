"""Samples statistics and real values for a single column.

Column and table names are dynamic, so they are composed through
psycopg.sql.Identifier. Never format an identifier into a query string.
"""

from __future__ import annotations

from psycopg import sql
from sqlalchemy import Engine

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.errors import ProfilingError

_STATS = sql.SQL("""
    SELECT count(DISTINCT {col}) AS distinct_count,
           avg(CASE WHEN {col} IS NULL THEN 1.0 ELSE 0.0 END) AS null_fraction
    FROM {tbl}
""")

_SAMPLES = sql.SQL("""
    SELECT DISTINCT {col}::text AS value
    FROM {tbl}
    WHERE {col} IS NOT NULL
    LIMIT %(limit)s
""")


class PostgresProfileReaderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile:
        col = sql.Identifier(column.column_name)
        tbl = sql.Identifier(column.schema_name, column.object_name)
        try:
            # Not merged into one `with` (SIM117): the inner cursor's cleanup
            # depends on the outer connection staying open through the whole
            # block; keeping them visually separate documents the two-level
            # cleanup the error path relies on.
            with self._engine.raw_connection() as raw:  # noqa: SIM117
                with raw.cursor() as cur:  # type: ignore[attr-defined]
                    cur.execute(_STATS.format(col=col, tbl=tbl))
                    distinct_count, null_fraction = cur.fetchone()
                    cur.execute(_SAMPLES.format(col=col, tbl=tbl), {"limit": sample_limit})
                    samples = tuple(row[0] for row in cur.fetchall())
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed domain error
            raise ProfilingError(column.qualified_name, str(exc)) from exc

        return ColumnProfile(
            datasource_name=column.datasource_name,
            schema_name=column.schema_name,
            object_name=column.object_name,
            column_name=column.column_name,
            distinct_count=distinct_count,
            null_fraction=float(null_fraction) if null_fraction is not None else None,
            sample_values=samples,
        )
