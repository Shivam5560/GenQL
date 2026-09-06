"""LLM-gateway providers: the OpenRouter/Cohere HTTP clients and the chat,
embedding, and rerank providers resolved through their registries by
`Settings`-named key.
"""

from __future__ import annotations

from dependency_injector import providers

import genql.repositories.gateway  # noqa: F401 - registration side effect
from genql.composition.core_container import CoreContainer
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.infrastructure.gateway.cohere_client import CohereClient
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.registry import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    RERANK_PROVIDERS,
)


def build_chat_provider(key: str, openrouter_client: OpenRouterClient, model: str) -> ChatProvider:
    return CHAT_PROVIDERS.create(key, client=openrouter_client, model=model)


def build_embedding_provider(
    key: str, openrouter_client: OpenRouterClient, model: str
) -> EmbeddingProvider:
    return EMBEDDING_PROVIDERS.create(key, client=openrouter_client, model=model)


def build_rerank_provider(
    key: str,
    enabled: bool,
    openrouter_client: OpenRouterClient,
    cohere_client: CohereClient,
    model: str,
) -> RerankProvider | None:
    if not enabled:
        return None
    client = openrouter_client if key == "openrouter" else cohere_client
    return RERANK_PROVIDERS.create(key, client=client, model=model)


class GatewayContainer(CoreContainer):
    openrouter_client = providers.Singleton(
        OpenRouterClient, api_key=CoreContainer.settings.provided.openrouter_api_key
    )
    cohere_client = providers.Singleton(
        CohereClient, api_key=CoreContainer.settings.provided.cohere_api_key
    )

    chat_provider = providers.Singleton(
        build_chat_provider,
        key=CoreContainer.settings.provided.chat_provider,
        openrouter_client=openrouter_client,
        model=CoreContainer.settings.provided.chat_model,
    )
    embedding_provider = providers.Singleton(
        build_embedding_provider,
        key=CoreContainer.settings.provided.embedding_provider,
        openrouter_client=openrouter_client,
        model=CoreContainer.settings.provided.embedding_model,
    )
    rerank_provider = providers.Singleton(
        build_rerank_provider,
        key=CoreContainer.settings.provided.rerank_provider,
        enabled=CoreContainer.settings.provided.rerank_enabled,
        openrouter_client=openrouter_client,
        cohere_client=cohere_client,
        model=CoreContainer.settings.provided.rerank_model,
    )
