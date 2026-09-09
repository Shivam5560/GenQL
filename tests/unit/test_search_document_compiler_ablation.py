"""The ablated document keeps every structural field and loses every enriched
one. Asserting both halves matters: a flag that dropped column names too would
ablate far more than 'descriptions' and would make the measured delta mean
something else entirely."""

from __future__ import annotations

from genql.repositories.semantic.search_document_repository import _content_for


def test_the_enriched_content_carries_descriptions_aliases_and_units() -> None:
    content = _content_for(
        object_name="store_sales",
        object_type="TABLE",
        domain_name="sales",
        description="one row per line item sold in a store",
        business_alias="POS line items",
        columns=[("ss_ext_sales_price", "extended sales price", "USD", ["1.00", "2.00"])],
        include_enrichment=True,
    )

    assert "one row per line item sold in a store" in content
    assert "POS line items" in content
    assert "USD" in content
    assert "extended sales price" in content


def test_the_ablated_content_keeps_structure_and_samples_but_drops_enrichment() -> None:
    content = _content_for(
        object_name="store_sales",
        object_type="TABLE",
        domain_name="sales",
        description="one row per line item sold in a store",
        business_alias="POS line items",
        columns=[("ss_ext_sales_price", "extended sales price", "USD", ["1.00", "2.00"])],
        include_enrichment=False,
    )

    assert "store_sales" in content
    assert "TABLE" in content
    assert "sales" in content
    assert "ss_ext_sales_price" in content
    assert "1.00" in content  # profiled samples are data, not LLM enrichment
    assert "one row per line item" not in content
    assert "POS line items" not in content
    assert "extended sales price" not in content
