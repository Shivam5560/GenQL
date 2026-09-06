"""Provenance is the vocabulary every enrichment-layer row carries."""

from __future__ import annotations

from genql.domain.value_objects.provenance import Provenance


def test_provenance_has_the_three_documented_values() -> None:
    assert {p.value for p in Provenance} == {"discovered", "llm", "yaml"}
