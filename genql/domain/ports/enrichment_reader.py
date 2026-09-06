from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class EnrichmentReader(Protocol):
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]: ...

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]: ...
