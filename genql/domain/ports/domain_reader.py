from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainReader(Protocol):
    """The read side of genql_domain, added in Phase 6 because domain scoping
    is the first caller that needs to go from a domain NAME (which retrieval
    hits carry) back to the id that SchemaLinker.link takes."""

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None: ...
