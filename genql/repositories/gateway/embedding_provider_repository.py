"""One request for the whole batch; vectors come back in input order."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_openai import OpenAIEmbeddings

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


@EMBEDDING_PROVIDERS.register("openai")
class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._embeddings = OpenAIEmbeddings(openai_api_key=api_key, model=model)

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        try:
            vectors = self._embeddings.embed_documents(list(texts))
        except Exception as exc:  # noqa: BLE001 - see OpenAIChatProvider.complete
            raise EmbeddingProviderError(f"OpenAI embedding request failed: {exc}") from exc
        return [tuple(vector) for vector in vectors]
