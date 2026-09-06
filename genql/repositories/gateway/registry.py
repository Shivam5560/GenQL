from __future__ import annotations

from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.registries.registry import Registry

CHAT_PROVIDERS: Registry[ChatProvider] = Registry("chat_providers")
EMBEDDING_PROVIDERS: Registry[EmbeddingProvider] = Registry("embedding_providers")
RERANK_PROVIDERS: Registry[RerankProvider] = Registry("rerank_providers")
