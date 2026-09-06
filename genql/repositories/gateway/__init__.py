"""Registers every LLM-gateway implementation with its registry.

This is the one place that imports the provider modules purely for their
`@CHAT_PROVIDERS.register(...)` / `@EMBEDDING_PROVIDERS.register(...)` /
`@RERANK_PROVIDERS.register(...)` decorator side effect.
"""

from __future__ import annotations

from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.repositories.gateway.embedding_provider_repository import OpenRouterEmbeddingProvider
from genql.repositories.gateway.rerank_provider_repository import (
    CohereRerankProvider,
    OpenRouterRerankProvider,
)

__all__ = [
    "OpenRouterChatProvider",
    "OpenRouterEmbeddingProvider",
    "OpenRouterRerankProvider",
    "CohereRerankProvider",
]
