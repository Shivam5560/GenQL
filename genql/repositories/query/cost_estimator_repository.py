"""EXPLAIN, in both of its forms, against a datasource's read-only binding.

One class implementing two ports. They share a connection path, a JSON plan
parser, and an error translation, and splitting them into two classes would
duplicate all three — but they are separate ports because their safety
profiles are opposite: `estimate` never runs the statement, `read_actuals`
runs it a second time. A caller holding only CostEstimator cannot reach the
expensive one.

`EXPLAIN (FORMAT JSON)` returns a single row holding a JSON array shaped
`[{"Plan": {...}}]`. psycopg decodes a json column into Python objects
already, but a driver or a server version that hands back the raw text is
cheap to tolerate, so both are handled.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.errors import CostEstimationError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider


def _plan(raw: Any) -> dict[str, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, list) or not payload:
        raise CostEstimationError(f"EXPLAIN returned an unexpected payload: {payload!r}")
    plan = payload[0].get("Plan")
    if not isinstance(plan, dict):
        raise CostEstimationError("EXPLAIN returned no Plan node")
    return plan


class PostgresCostEstimator:
    def __init__(
        self, provider: DatasourceEngineProvider, datasources: DatasourceRepository
    ) -> None:
        self._provider = provider
        self._datasources = datasources

    def estimate(self, sql: str, datasource_name: str) -> float:
        plan = self._explain(f"EXPLAIN (FORMAT JSON) {sql}", datasource_name)
        cost = plan.get("Total Cost")
        if not isinstance(cost, int | float):
            raise CostEstimationError("EXPLAIN returned no Total Cost")
        return float(cost)

    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        plan = self._explain(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", datasource_name)
        return ExecutionActuals(
            total_time_ms=float(plan.get("Actual Total Time", 0.0)),
            rows=int(plan.get("Actual Rows", 0)),
            shared_buffers_hit=int(plan.get("Shared Hit Blocks", 0)),
            shared_buffers_read=int(plan.get("Shared Read Blocks", 0)),
        )

    def _explain(self, statement: str, datasource_name: str) -> dict[str, Any]:
        datasource = self._datasources.get(datasource_name)
        engine = self._provider.readonly_engine_for(datasource)
        try:
            with engine.begin() as conn:
                raw = conn.execute(text(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise CostEstimationError(f"EXPLAIN failed: {exc}") from exc
        return _plan(raw)
