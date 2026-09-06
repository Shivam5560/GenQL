"""Binds a question to concrete identifiers.

Deliberately not an LLM port: the implementation composes Phase 4's retrieval
with the semantic store's own columns, join paths, and metrics. The parent
spec's correctness test for the offline/online split — retrieval and schema
linking still work with every LLM provider unreachable — holds only if this
stage never calls a model.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.schema_link import SchemaLink


@runtime_checkable
class SchemaLinker(Protocol):
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]: ...
