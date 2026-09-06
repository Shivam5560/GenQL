"""Runs the validated statement under the configured row cap.

The parent spec's §9 stage 12 and §12's execution rules. The three safety
properties are split by layer on purpose: the read-only role is the engine
binding's job (infrastructure), the statement timeout is the repository's
(it needs a transaction), the row cap is this service's (it is configuration),
and the injected LIMIT is a guardrail's. No single layer can quietly drop all
four.

An unknown datasource is not translated: UnknownDatasourceError already names
the registered alternatives, and re-wrapping it as an execution failure would
lose that.
"""

from __future__ import annotations

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.query_executor_factory import QueryExecutorFactory


class GuardedExecutionService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        executors: QueryExecutorFactory,
        row_cap: int,
    ) -> None:
        self._datasources = datasources
        self._executors = executors
        self._row_cap = row_cap

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        datasource = self._datasources.get(datasource_name)
        return self._executors.for_datasource(datasource).execute(sql, self._row_cap)
