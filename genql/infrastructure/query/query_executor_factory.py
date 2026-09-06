"""Binds a QueryExecutor to one datasource's READ-ONLY engine.

This file is the entire reason the admin engine is unreachable from the
execution path: it calls `readonly_engine_for` and nothing else, and it is the
only place a QueryExecutor is ever constructed. A future caller that wanted an
admin-privileged executor would have to add a second factory, which is a
reviewable change rather than a silent one.
"""

from __future__ import annotations

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.query_executor import QueryExecutor
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.query.query_executor_repository import ReadOnlyQueryExecutorRepository


class QueryExecutorFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider, statement_timeout_ms: int) -> None:
        self._provider = provider
        self._statement_timeout_ms = statement_timeout_ms

    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        return ReadOnlyQueryExecutorRepository(
            self._provider.readonly_engine_for(datasource),
            statement_timeout_ms=self._statement_timeout_ms,
        )
