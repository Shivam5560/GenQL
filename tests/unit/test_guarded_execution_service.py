"""The service resolves the datasource, hands the SQL to the executor bound to
it, and applies the configured row cap. The cap assertion is the important
one: a service that forgets to pass it would make the executor's truncation
logic unreachable."""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import ExecutionError, UnknownDatasourceError
from genql.domain.ports.query_executor import QueryExecutor
from genql.services.query.guarded_execution_service import GuardedExecutionService

DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
RESULT = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        self.calls.append((sql, row_cap))
        return RESULT


class RaisingExecutor:
    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        raise ExecutionError("canceling statement due to statement timeout")


class FixedExecutorFactory:
    def __init__(self, executor: QueryExecutor) -> None:
        self.executor = executor
        self.datasources: list[str] = []

    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        self.datasources.append(datasource.name)
        return self.executor


class FakeDatasourceRepository:
    def __init__(self, datasource: Datasource | None) -> None:
        self._datasource = datasource

    def add(self, datasource: Datasource) -> None:
        raise NotImplementedError

    def get(self, name: str) -> Datasource:
        if self._datasource is None:
            raise UnknownDatasourceError(name, [])
        return self._datasource

    def list_all(self, enabled_only: bool = False) -> list[Datasource]:
        return [self._datasource] if self._datasource else []

    def remove(self, name: str) -> None:
        raise NotImplementedError


def test_the_configured_row_cap_is_passed_to_the_executor() -> None:
    executor = RecordingExecutor()
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS),
        executors=FixedExecutorFactory(executor),
        row_cap=250,
    )

    result = service.execute("SELECT 1 LIMIT 1", "local")

    assert executor.calls == [("SELECT 1 LIMIT 1", 250)]
    assert result is RESULT


def test_the_executor_is_resolved_for_the_datasource_asked_for() -> None:
    factory = FixedExecutorFactory(RecordingExecutor())
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS), executors=factory, row_cap=10
    )

    service.execute("SELECT 1", "local")

    assert factory.datasources == ["local"]


def test_an_executor_failure_propagates_as_an_execution_error() -> None:
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS),
        executors=FixedExecutorFactory(RaisingExecutor()),
        row_cap=10,
    )

    with pytest.raises(ExecutionError, match="timeout"):
        service.execute("SELECT pg_sleep(5)", "local")


def test_an_unknown_datasource_stays_an_unknown_datasource_error() -> None:
    """Not translated: a misspelled --datasource is the caller's mistake, not a
    failure of execution, and the existing error already says which names exist."""
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(None),
        executors=FixedExecutorFactory(RecordingExecutor()),
        row_cap=10,
    )

    with pytest.raises(UnknownDatasourceError):
        service.execute("SELECT 1", "nope")
