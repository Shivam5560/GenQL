"""Persists mined join paths, one upsert per path."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.join_path import JoinPath

_UPSERT = text("""
    INSERT INTO genql.genql_join_path
        (datasource_name, schema_name, source_object, target_object, path, weight, provenance)
    VALUES (:datasource_name, :schema_name, :source_object, :target_object, :path, :weight,
            :provenance)
    ON CONFLICT ON CONSTRAINT pk_genql_join_path DO UPDATE
        SET path = EXCLUDED.path,
            weight = EXCLUDED.weight,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
""")


class PostgresJoinPathWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, paths: Sequence[JoinPath]) -> int:
        if not paths:
            return 0
        rows = [p.model_dump(mode="json") for p in paths]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT, rows)
        return len(rows)
