"""All three share one rule — an overlay value always wins — kept as
separate classes so a future kind needing different validation costs one
new file, not a branch in an existing one."""

from __future__ import annotations

import pytest

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.value_objects.provenance import Provenance
from genql.repositories.semantic.enricher_repository import (
    AliasEnricher,
    DescriptionEnricher,
    UnitEnricher,
)

DISCOVERED = EnrichmentField(
    kind="description",
    qualified_name="local.shop.orders",
    value="from LLM",
    provenance=Provenance.LLM,
)
OVERLAY = EnrichmentField(
    kind="description",
    qualified_name="local.shop.orders",
    value="from YAML",
    provenance=Provenance.YAML,
)


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_overlay_wins_when_present(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(DISCOVERED, OVERLAY) is OVERLAY


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_discovered_passes_through_when_no_overlay(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(DISCOVERED, None) is DISCOVERED


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_none_when_neither_exists(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(None, None) is None


def test_keys_are_distinct() -> None:
    assert {DescriptionEnricher.key, AliasEnricher.key, UnitEnricher.key} == {
        "description",
        "alias",
        "unit",
    }
