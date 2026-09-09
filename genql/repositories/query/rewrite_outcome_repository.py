"""Appends one measured execution.

The entity carries `datasource_name` and the table stores `datasource_id`, so
the name is resolved here rather than by the service: a service that knew the
integer key would be holding a persistence detail. `datasource_id` is TEXT
keyed on `genql_datasource.name` (that table's real primary key is `name`,
not a surrogate id), so the resolved value is `datasource.name` itself.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.errors import OptimizationError
from genql.domain.ports.datasource_repository import DatasourceRepository

_INSERT = text("""
    INSERT INTO genql.genql_rewrite_outcome
        (sql_hash, datasource_id, rules_applied, estimated_cost, actual_total_time_ms,
         actual_rows, shared_buffers_hit, shared_buffers_read)
    VALUES
        (:sql_hash, :datasource_id, :rules_applied, :estimated_cost, :actual_total_time_ms,
         :actual_rows, :shared_buffers_hit, :shared_buffers_read)
""")


class PostgresRewriteOutcomeWriter:
    def __init__(self, engine: Engine, datasources: DatasourceRepository) -> None:
        self._engine = engine
        self._datasources = datasources

    def write(self, outcome: RewriteOutcome) -> None:
        datasource = self._datasources.get(outcome.datasource_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "sql_hash": outcome.sql_hash,
                        "datasource_id": datasource.name,
                        "rules_applied": list(outcome.rules_applied),
                        "estimated_cost": outcome.estimated_cost,
                        "actual_total_time_ms": outcome.actuals.total_time_ms,
                        "actual_rows": outcome.actuals.rows,
                        "shared_buffers_hit": outcome.actuals.shared_buffers_hit,
                        "shared_buffers_read": outcome.actuals.shared_buffers_read,
                    },
                )
        except SQLAlchemyError as exc:
            raise OptimizationError(f"failed to record a rewrite outcome: {exc}") from exc
