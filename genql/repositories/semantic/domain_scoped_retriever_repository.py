"""Wraps another Retriever and requires domain_id — for the online
pipeline's future 'domain already resolved, now search only inside it'
case. Refusing to silently no-op on a missing domain_id is the point of
giving this its own type rather than treating domain scoping as just
another optional filter everywhere."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import RetrievalError
from genql.domain.ports.retriever import Retriever, SearchResult
from genql.repositories.semantic.registry import RETRIEVERS


@RETRIEVERS.register("domain_scoped")
class DomainScopedRetriever:
    def __init__(self, inner: Retriever) -> None:
        self._inner = inner

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        if domain_id is None:
            raise RetrievalError("domain_scoped retrieval requires a domain_id")
        return self._inner.search(datasource_name, query, query_embedding, top_k, domain_id)
