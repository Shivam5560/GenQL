from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.object_enrichment import ObjectEnrichment


@runtime_checkable
class DomainNamer(Protocol):
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]: ...
