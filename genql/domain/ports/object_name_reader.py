"""Every `schema.object` the semantic store knows for one datasource.

Datasource-wide, unlike SemanticCatalogReader's per-SchemaRef reads: the
object allowlist has to reject a table in *any* unregistered schema, so it
cannot be built one schema at a time.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectNameReader(Protocol):
    def read_object_names(self, datasource_name: str) -> frozenset[str]: ...
