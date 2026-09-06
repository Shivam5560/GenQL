"""YAML-authored metrics, upserted by (datasource_name, name) and read back by datasource."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.metric import Metric

_UPSERT_METRIC = text("""
    INSERT INTO genql.genql_metric
        (datasource_name, name, sql_expression, grain, unit, default_filters, provenance)
    VALUES (:datasource_name, :name, :sql_expression, :grain, :unit,
            CAST(:default_filters AS JSONB), :provenance)
    ON CONFLICT ON CONSTRAINT uq_genql_metric_identity DO UPDATE
        SET sql_expression = EXCLUDED.sql_expression,
            grain = EXCLUDED.grain,
            unit = EXCLUDED.unit,
            default_filters = EXCLUDED.default_filters,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
""")

_SELECT_METRICS = text("""
    SELECT datasource_name, name, sql_expression, grain, unit, default_filters, provenance
    FROM genql.genql_metric
    WHERE datasource_name = :datasource_name
    ORDER BY name
""")


class PostgresMetricRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, metrics: Sequence[Metric]) -> int:
        if not metrics:
            return 0
        rows = [m.model_dump(mode="json") for m in metrics]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_METRIC, rows)
        return len(rows)

    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_METRICS, {"datasource_name": datasource_name}).all()
        return [Metric.model_validate(r._mapping) for r in rows]  # noqa: SLF001
