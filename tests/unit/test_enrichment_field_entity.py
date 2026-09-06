from __future__ import annotations

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.value_objects.provenance import Provenance


def test_kind_is_restricted_to_the_three_merge_time_fields() -> None:
    field = EnrichmentField(
        kind="description",
        qualified_name="local.tpcds.store_sales",
        value="x",
        provenance=Provenance.LLM,
    )

    assert field.kind == "description"
