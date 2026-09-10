"""Schema linking is deterministic composition, not generation: retrieval says
which objects, the semantic store says which columns, which mined join paths,
and which metrics. No ChatProvider appears anywhere in this test, which is the
parent spec's stated correctness test for the offline/online split."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.column import Column
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.errors import SchemaLinkingError
from genql.domain.ports.retriever import SearchResult
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.query.schema_linking_service import SchemaLinkingService
from genql.services.semantic.retrieval_service import RetrievalService

RESULTS = [
    SearchResult(
        datasource_name="local",
        schema_name="shop",
        object_name="orders",
        domain_name="sales",
        score=1.0,
    ),
    SearchResult(
        datasource_name="local",
        schema_name="shop",
        object_name="customers",
        domain_name="sales",
        score=0.5,
    ),
]


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeRetriever:
    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = results

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return self._results


class FakeSemanticCatalogReader:
    def __init__(self) -> None:
        self.refs: list[SchemaRef] = []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        self.refs.append(ref)
        return [
            Column(
                datasource_name="local",
                schema_name="shop",
                object_name="orders",
                column_name="total",
                ordinal=1,
                data_type="numeric",
                is_nullable=False,
            ),
            Column(
                datasource_name="local",
                schema_name="shop",
                object_name="customers",
                column_name="email",
                ordinal=1,
                data_type="text",
                is_nullable=True,
            ),
        ]


class FakeJoinPathReader:
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return [
            JoinPath(
                datasource_name="local",
                schema_name="shop",
                source_object="orders",
                target_object="customers",
                path=("orders", "customers"),
                weight=1.0,
            )
        ]


class FakeMetricReader:
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        return [
            Metric(
                datasource_name="local",
                name="net_revenue",
                sql_expression="sum(orders.total)",
                grain="day",
            ),
            Metric(
                datasource_name="local",
                name="stock_on_hand",
                sql_expression="sum(inventory.qty)",
                grain="day",
            ),
        ]


def _service(
    results: Sequence[SearchResult] = RESULTS,
    reader: FakeSemanticCatalogReader | None = None,
) -> SchemaLinkingService:
    return SchemaLinkingService(
        retrieval=RetrievalService(FakeEmbeddingProvider(), FakeRetriever(results), rerank=None),
        reader=reader or FakeSemanticCatalogReader(),
        join_paths=FakeJoinPathReader(),
        metrics=FakeMetricReader(),
        top_k=10,
    )


def test_one_link_is_produced_per_retrieved_object() -> None:
    links = _service().link("revenue by customer", "local")

    assert [link.object_qualified_name for link in links] == [
        "local.shop.orders",
        "local.shop.customers",
    ]


def test_columns_are_bound_to_the_object_they_belong_to() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].column_names == ("total",)
    assert links[1].column_names == ("email",)


def test_join_paths_are_bound_to_both_ends() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].join_paths == ("orders->customers",)
    assert links[1].join_paths == ("orders->customers",)


def test_a_metric_is_bound_to_the_object_its_expression_names() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].metric_names == ("net_revenue",)
    assert links[1].metric_names == ()


def test_each_schema_is_read_once_however_many_objects_it_contributed() -> None:
    reader = FakeSemanticCatalogReader()

    _service(reader=reader).link("revenue by customer", "local")

    assert reader.refs == [SchemaRef(datasource_name="local", schema_name="shop")]


def test_zero_retrieval_results_is_a_typed_failure() -> None:
    with pytest.raises(SchemaLinkingError, match="revenue by customer"):
        _service(results=[]).link("revenue by customer", "local")


class SpyRetrieval:
    """Records whether reranking was requested, ignoring embedding/retriever
    plumbing entirely — schema_linking's rerank=False choice is the only
    thing this test cares about."""

    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = results
        self.reranked: list[bool] = []

    def search(
        self,
        datasource_name: str,
        query: str,
        top_k: int,
        domain_id: int | None = None,
        *,
        rerank: bool = True,
    ) -> Sequence[SearchResult]:
        self.reranked.append(rerank)
        return self._results


def test_schema_linking_does_not_pay_for_reranking() -> None:
    """HybridRrfRetriever applies LIMIT top_k inside its own SQL, so rerank
    can only reorder an already-fixed candidate set — and link() returns
    every one of those objects regardless of order. Reranking would spend a
    full provider round trip on every turn to influence a rendering position
    nothing downstream depends on."""
    retrieval = SpyRetrieval(RESULTS)

    SchemaLinkingService(
        retrieval=retrieval,  # type: ignore[arg-type]
        reader=FakeSemanticCatalogReader(),
        join_paths=FakeJoinPathReader(),
        metrics=FakeMetricReader(),
        top_k=10,
    ).link("revenue by customer", "local")

    assert retrieval.reranked == [False]
