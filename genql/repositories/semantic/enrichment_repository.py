"""Object and column enrichment, read and written together — one aggregate."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef


# No pgvector adapter is registered on this engine (it's created from a plain
# DSN via SQLAlchemy, with no `register_vector` hook) — nothing else in this
# codebase reads a `vector` column's value back into Python, only ever uses
# it inside a SQL distance expression (see DenseRetriever), so this is the
# first read path to hit it. Without an adapter, psycopg returns the column
# as pgvector's own text wire format, `"[0.1,0.2,...]"`, not a Python
# sequence — `tuple(that_string)` would silently iterate its characters.
def _parse_embedding(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(float(x) for x in value.strip("[]").split(",") if x)
    return tuple(value)


_SELECT_OBJECT_ENRICHMENTS = text("""
    SELECT datasource_name, schema_name, object_name, description, business_alias,
           provenance, confidence, embedding
    FROM genql.genql_object_enrichment
    WHERE datasource_name = :datasource_name
""")

_UPSERT_OBJECT_ENRICHMENT = text("""
    INSERT INTO genql.genql_object_enrichment
        (datasource_name, schema_name, object_name, description, business_alias, provenance,
         confidence, embedding)
    VALUES (:datasource_name, :schema_name, :object_name, :description, :business_alias,
            :provenance, :confidence, :embedding)
    ON CONFLICT ON CONSTRAINT pk_genql_object_enrichment DO UPDATE
        SET description = EXCLUDED.description,
            business_alias = EXCLUDED.business_alias,
            provenance = EXCLUDED.provenance,
            confidence = EXCLUDED.confidence,
            embedding = EXCLUDED.embedding,
            discovered_at = now()
""")

_SELECT_COLUMN_ENRICHMENTS = text("""
    SELECT datasource_name, schema_name, object_name, column_name, description, business_alias,
           unit, provenance, confidence
    FROM genql.genql_column_enrichment
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_UPSERT_COLUMN_ENRICHMENT = text("""
    INSERT INTO genql.genql_column_enrichment
        (datasource_name, schema_name, object_name, column_name, description, business_alias,
         unit, provenance, confidence)
    VALUES (:datasource_name, :schema_name, :object_name, :column_name, :description,
            :business_alias, :unit, :provenance, :confidence)
    ON CONFLICT ON CONSTRAINT pk_genql_column_enrichment DO UPDATE
        SET description = EXCLUDED.description,
            business_alias = EXCLUDED.business_alias,
            unit = EXCLUDED.unit,
            provenance = EXCLUDED.provenance,
            confidence = EXCLUDED.confidence,
            discovered_at = now()
""")


class PostgresEnrichmentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_OBJECT_ENRICHMENTS, {"datasource_name": datasource_name}
            ).all()
        return [
            ObjectEnrichment.model_validate(
                {
                    **r._mapping,  # noqa: SLF001
                    "embedding": _parse_embedding(r._mapping["embedding"]) or None,  # noqa: SLF001
                }
            )
            for r in rows
        ]

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_COLUMN_ENRICHMENTS, ref.model_dump()).all()
        return [ColumnEnrichment.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_OBJECT_ENRICHMENT, enrichment.model_dump(mode="json"))

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        if not enrichments:
            return 0
        rows = [e.model_dump(mode="json") for e in enrichments]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_COLUMN_ENRICHMENT, rows)
        return len(rows)
