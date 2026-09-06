"""Runs one validated statement under a row cap and returns its rows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.execution_result import ExecutionResult


@runtime_checkable
class QueryExecutor(Protocol):
    def execute(self, sql: str, row_cap: int) -> ExecutionResult: ...
