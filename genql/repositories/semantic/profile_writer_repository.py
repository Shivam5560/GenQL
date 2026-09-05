"""Persists column profiles into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column_profile import ColumnProfile

_UPSERT = text("""
    INSERT INTO genql.genql_column_profile
        (schema_name, object_name, column_name, distinct_count, null_fraction, sample_values)
    VALUES (:schema_name, :object_name, :column_name,
            :distinct_count, :null_fraction, :sample_values)
    ON CONFLICT ON CONSTRAINT uq_genql_profile_identity DO UPDATE
        SET distinct_count = EXCLUDED.distinct_count,
            null_fraction = EXCLUDED.null_fraction,
            sample_values = EXCLUDED.sample_values,
            profiled_at = now()
""")


class PostgresProfileWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int:
        if not profiles:
            return 0
        payload = [
            {
                "schema_name": p.schema_name,
                "object_name": p.object_name,
                "column_name": p.column_name,
                "distinct_count": p.distinct_count,
                "null_fraction": p.null_fraction,
                "sample_values": list(p.sample_values),
            }
            for p in profiles
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT, payload)
        return len(payload)
