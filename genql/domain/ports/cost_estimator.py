"""Predicts a statement's cost without running it.

`EXPLAIN` without `ANALYZE` never executes the statement, which is what makes
this port as safe as static validation rather than as consequential as guarded
execution — the distinction that lets the cost gate sit before execution
rather than after it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CostEstimator(Protocol):
    def estimate(self, sql: str, datasource_name: str) -> float: ...
