"""Measures a statement by running it under `EXPLAIN (ANALYZE, BUFFERS)`.

A separate port from CostEstimator despite sharing an implementation class,
because the two have opposite safety profiles: estimating is free and never
executes, measuring re-runs the whole statement and doubles its cost. A caller
that holds only CostEstimator structurally cannot start a second execution.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.execution_actuals import ExecutionActuals


@runtime_checkable
class ExecutionActualsReader(Protocol):
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals: ...
