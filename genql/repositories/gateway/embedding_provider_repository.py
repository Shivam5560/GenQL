"""One request for the whole batch; vectors come back in input order."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import EmbeddingProviderError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import EMBEDDING_PROVIDERS


@EMBEDDING_PROVIDERS.register("openrouter")
class OpenRouterEmbeddingProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        try:
            body = self._client.post_json(
                "/embeddings", {"model": self._model, "input": list(texts)}
            )
            return [tuple(row["embedding"]) for row in body["data"]]
        except (OpenRouterError, KeyError) as exc:
            raise EmbeddingProviderError(f"OpenRouter embedding request failed: {exc}") from exc
