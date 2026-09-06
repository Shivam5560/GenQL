"""Embeds the question once, retrieves through whichever Retriever key
Settings.retriever names, and reranks unless reranking is disabled — a
config-only toggle, per the parent spec's stated reason for giving rerank
its own port."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import EmbeddingProviderError, RerankProviderError, RetrievalError
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.domain.ports.retriever import Retriever, SearchResult


class RetrievalService:
    def __init__(
        self, embedder: EmbeddingProvider, retriever: Retriever, rerank: RerankProvider | None
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._rerank = rerank

    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        try:
            query_embedding = self._embedder.embed([query])[0]
        except EmbeddingProviderError as exc:
            raise RetrievalError(f"failed to embed query: {exc}") from exc

        results = self._retriever.search(datasource_name, query, query_embedding, top_k, domain_id)
        if self._rerank is None or not results:
            return results

        documents = [f"{r.schema_name}.{r.object_name} (domain: {r.domain_name})" for r in results]
        try:
            scores = self._rerank.rerank(query, documents, top_n=len(results))
        except RerankProviderError as exc:
            raise RetrievalError(f"failed to rerank results: {exc}") from exc
        return [results[s.index] for s in sorted(scores, key=lambda s: s.score, reverse=True)]
