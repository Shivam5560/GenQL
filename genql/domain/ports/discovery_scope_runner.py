"""The discovery pipeline as the ingestion service sees it.

`DiscoveryRunner` lives in `genql.discovery`, which is not part of the
api/services/domain layering, so the service depends on this protocol instead
of on that class — the same treatment every other collaborator gets.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.scope_run_result import ScopeRunResult


class DiscoveryScopeRunner(Protocol):
    def run_scope(
        self, scope: QueryScope, sample_limit: int, start_from: str | None = None
    ) -> Sequence[ScopeRunResult]: ...
