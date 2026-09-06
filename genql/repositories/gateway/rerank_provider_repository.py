"""OpenRouterRerankProvider and CohereRerankProvider — both registered from
day one, per the parent spec's stated fallback."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import RerankProviderError
from genql.domain.ports.rerank_provider import RerankScore
from genql.infrastructure.gateway.cohere_client import CohereClient, CohereError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import RERANK_PROVIDERS


@RERANK_PROVIDERS.register("openrouter")
class OpenRouterRerankProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        try:
            body = self._client.post_json(
                "/rerank",
                {
                    "model": self._model,
                    "query": query,
                    "documents": list(documents),
                    "top_n": top_n,
                },
            )
            return [
                RerankScore(index=r["index"], score=r["relevance_score"]) for r in body["results"]
            ]
        except (OpenRouterError, KeyError) as exc:
            raise RerankProviderError(f"OpenRouter rerank request failed: {exc}") from exc


@RERANK_PROVIDERS.register("cohere")
class CohereRerankProvider:
    def __init__(self, client: CohereClient, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        try:
            body = self._client.post_json(
                "/rerank",
                {
                    "model": self._model,
                    "query": query,
                    "documents": list(documents),
                    "top_n": top_n,
                },
            )
            return [
                RerankScore(index=r["index"], score=r["relevance_score"]) for r in body["results"]
            ]
        except (CohereError, KeyError) as exc:
            raise RerankProviderError(f"Cohere rerank request failed: {exc}") from exc
