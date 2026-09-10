"""Embeds the question once, retrieves through whichever Retriever key
Settings.retriever names, and reranks unless reranking is disabled — a
config-only toggle, per the parent spec's stated reason for giving rerank
its own port.

Two call-count reductions live here, both deterministic.

First, the query embedding is memoised on the query text. One analytical turn
calls `search` twice with the *same* question — DomainScopingService samples
unscoped to vote on a domain, then SchemaLinkingService searches scoped to the
winner — and embedding a string is a pure function of that string and the
model, so the second call was paying a provider round trip for a vector it had
already computed. The cache is bounded and keyed on the exact query text; a
Singleton RetrievalService means it also spans turns, which is a bonus rather
than the point.

Second, `rerank` is a per-call argument, not only a wiring-time one. A caller
that consumes the result *set* rather than its order — DomainScopingService
takes a plurality vote over the domain each hit carries — gets nothing from
reranking but pays a full provider round trip for it. Ordering still reaches
the one caller that ranks (schema linking), so this removes a call without
removing a signal.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence

from genql.domain.errors import EmbeddingProviderError, RerankProviderError, RetrievalError
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.domain.ports.retriever import Retriever, SearchResult

# Large enough that both passes of a turn hit, and that a short interactive
# session re-asking the same question hits; small enough that an unbounded
# stream of distinct questions cannot grow the process without limit.
_EMBEDDING_CACHE_MAX = 128


class RetrievalService:
    def __init__(
        self, embedder: EmbeddingProvider, retriever: Retriever, rerank: RerankProvider | None
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._rerank = rerank
        self._embedding_cache: OrderedDict[str, Sequence[float]] = OrderedDict()

    def search(
        self,
        datasource_name: str,
        query: str,
        top_k: int,
        domain_id: int | None = None,
        *,
        rerank: bool = True,
    ) -> Sequence[SearchResult]:
        query_embedding = self._embed(query)

        results = self._retriever.search(datasource_name, query, query_embedding, top_k, domain_id)
        if self._rerank is None or not rerank or not results:
            return results

        documents = [f"{r.schema_name}.{r.object_name} (domain: {r.domain_name})" for r in results]
        try:
            scores = self._rerank.rerank(query, documents, top_n=len(results))
        except RerankProviderError as exc:
            raise RetrievalError(f"failed to rerank results: {exc}") from exc
        return [results[s.index] for s in sorted(scores, key=lambda s: s.score, reverse=True)]

    def _embed(self, query: str) -> Sequence[float]:
        cached = self._embedding_cache.get(query)
        if cached is not None:
            self._embedding_cache.move_to_end(query)
            return cached
        try:
            embedding = self._embedder.embed([query])[0]
        except EmbeddingProviderError as exc:
            raise RetrievalError(f"failed to embed query: {exc}") from exc
        self._embedding_cache[query] = embedding
        if len(self._embedding_cache) > _EMBEDDING_CACHE_MAX:
            self._embedding_cache.popitem(last=False)
        return embedding
