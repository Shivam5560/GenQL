from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment


@runtime_checkable
class EnrichmentWriter(Protocol):
    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None: ...

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int: ...
