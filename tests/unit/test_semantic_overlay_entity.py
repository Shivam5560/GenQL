"""Validates the shape of one semantic/<datasource>.yaml file. Object keys
are fully-qualified "schema.object" strings; parsing them apart is the
overlay service's job, not this model's."""

from __future__ import annotations

from genql.domain.entities.semantic_overlay import (
    ColumnOverlay,
    JoinHintOverlay,
    MetricOverlay,
    ObjectOverlay,
    SemanticOverlay,
)


def test_round_trips_a_full_overlay() -> None:
    overlay = SemanticOverlay(
        datasource="local",
        objects={
            "tpcds.store_sales": ObjectOverlay(
                description="Point-of-sale line items for in-store purchases.",
                business_alias="store transactions",
                columns={
                    "ss_ext_sales_price": ColumnOverlay(
                        description="Extended sales price before discount.", unit="USD"
                    )
                },
            )
        },
        metrics=(
            MetricOverlay(
                name="net_sales",
                sql_expression="ss_ext_sales_price - ss_ext_discount_amt",
                grain="line_item",
                unit="USD",
            ),
        ),
        join_hints=(
            JoinHintOverlay(
                source_object="tpcds.store_sales",
                target_object="tpcds.customer",
                path=("tpcds.store_sales", "tpcds.customer"),
                weight=0.5,
            ),
        ),
    )

    assert overlay.objects["tpcds.store_sales"].columns["ss_ext_sales_price"].unit == "USD"
    assert overlay.metrics[0].name == "net_sales"
    assert overlay.join_hints[0].path == ("tpcds.store_sales", "tpcds.customer")


def test_objects_metrics_and_join_hints_default_empty() -> None:
    overlay = SemanticOverlay(datasource="local")

    assert overlay.objects == {}
    assert overlay.metrics == ()
    assert overlay.join_hints == ()
