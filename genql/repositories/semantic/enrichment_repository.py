"""Object and column enrichment, read and written together — one aggregate."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef

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
                    **r._mapping,
                    "embedding": tuple(r._mapping["embedding"] or ())  # noqa: SLF001
                    or None,
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
