"""Frozen, and confidence is bounded to [0, 1] like every other confidence
field in the codebase."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.provenance import Provenance


def test_defaults_are_llm_provenance_and_full_confidence() -> None:
    enrichment = ObjectEnrichment(
        datasource_name="local",
        schema_name="tpcds",
        object_name="store_sales",
        description="Point-of-sale line items.",
    )

    assert enrichment.provenance == Provenance.LLM
    assert enrichment.confidence == 1.0
    assert enrichment.embedding is None
    assert enrichment.qualified_name == "local.tpcds.store_sales"


def test_confidence_above_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ObjectEnrichment(
            datasource_name="local",
            schema_name="tpcds",
            object_name="store_sales",
            description="x",
            confidence=1.5,
        )


def test_is_frozen() -> None:
    enrichment = ObjectEnrichment(
        datasource_name="local",
        schema_name="tpcds",
        object_name="store_sales",
        description="x",
    )
    with pytest.raises(ValidationError):
        enrichment.description = "y"  # type: ignore[misc]
