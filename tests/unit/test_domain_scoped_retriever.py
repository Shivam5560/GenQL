from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.errors import RetrievalError
from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.domain_scoped_retriever_repository import DomainScopedRetriever

RESULT = SearchResult(
    datasource_name="local", schema_name="shop", object_name="a", domain_name="sales", score=1.0
)


class FakeInner:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        assert domain_id is not None
        return [RESULT]


def test_requires_a_domain_id() -> None:
    retriever = DomainScopedRetriever(FakeInner())

    with pytest.raises(RetrievalError):
        retriever.search("local", "q", (0.1,), 10, domain_id=None)


def test_forwards_to_the_inner_retriever_when_domain_id_is_given() -> None:
    retriever = DomainScopedRetriever(FakeInner())

    results = retriever.search("local", "q", (0.1,), 10, domain_id=7)

    assert results == [RESULT]
