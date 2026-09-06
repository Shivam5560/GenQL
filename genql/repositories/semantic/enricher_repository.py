"""The default merge rule — an overlay value always wins; absent an
overlay, the discovered value passes through unchanged — is identical
across all three registered kinds."""

from __future__ import annotations

from typing import ClassVar

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.repositories.semantic.registry import ENRICHERS


@ENRICHERS.register("description")
class DescriptionEnricher:
    key: ClassVar[str] = "description"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered


@ENRICHERS.register("alias")
class AliasEnricher:
    key: ClassVar[str] = "alias"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered


@ENRICHERS.register("unit")
class UnitEnricher:
    key: ClassVar[str] = "unit"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered
