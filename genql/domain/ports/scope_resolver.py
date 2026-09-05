"""Turns optional user input into a concrete QueryScope.

Phase 5 registers an LLM-backed resolver that picks the datasource from a
natural-language question. It implements this same protocol, so no call site
changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.value_objects.query_scope import QueryScope


@runtime_checkable
class ScopeResolver(Protocol):
    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope: ...
