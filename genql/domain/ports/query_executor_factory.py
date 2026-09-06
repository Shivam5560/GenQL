"""Binds a QueryExecutor to one datasource's read-only engine.

The only implementation resolves the read-only binding, never the admin one,
which is what makes the admin engine structurally unreachable from the
execution path rather than merely unused by convention.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.query_executor import QueryExecutor


@runtime_checkable
class QueryExecutorFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> QueryExecutor: ...
