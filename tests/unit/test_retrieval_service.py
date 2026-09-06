"""Embeds once, retrieves through whichever Retriever is injected, reranks
unless reranking is disabled by configuration (rerank=None)."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.ports.rerank_provider import RerankScore
from genql.domain.ports.retriever import SearchResult
from genql.services.semantic.retrieval_service import RetrievalService

RESULTS = [
    SearchResult(
        datasource_name="local", schema_name="shop", object_name="a", domain_name=None, score=1.0
    ),
    SearchResult(
        datasource_name="local", schema_name="shop", object_name="b", domain_name=None, score=0.5
    ),
]


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeRetriever:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return RESULTS


class FakeRerankProvider:
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        return [RerankScore(index=1, score=0.9), RerankScore(index=0, score=0.1)]


def test_search_without_rerank_returns_the_retriever_order() -> None:
    service = RetrievalService(FakeEmbeddingProvider(), FakeRetriever(), rerank=None)

    results = service.search("local", "how many orders", top_k=10)

    assert [r.object_name for r in results] == ["a", "b"]


def test_search_with_rerank_reorders_by_rerank_score() -> None:
    service = RetrievalService(FakeEmbeddingProvider(), FakeRetriever(), FakeRerankProvider())

    results = service.search("local", "how many orders", top_k=10)

    assert [r.object_name for r in results] == ["b", "a"]
