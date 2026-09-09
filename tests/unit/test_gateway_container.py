"""`build_chat_provider`/`build_embedding_provider`/`build_rerank_provider`
resolve each registered key to its own constructor shape via a lookup
table, not a branch — this pins that resolution without any network call."""

from __future__ import annotations

from genql.composition.gateway_container import (
    build_chat_provider,
    build_embedding_provider,
    build_rerank_provider,
)
from genql.infrastructure.gateway.cohere_client import CohereClient
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import (
    OpenAIChatProvider,
    OpenRouterChatProvider,
)
from genql.repositories.gateway.embedding_provider_repository import (
    OpenAIEmbeddingProvider,
    OpenRouterEmbeddingProvider,
)
from genql.repositories.gateway.rerank_provider_repository import CohereRerankProvider


def test_build_chat_provider_resolves_openai_key_to_its_own_constructor_shape() -> None:
    provider = build_chat_provider(
        "openai",
        openrouter_client=OpenRouterClient(api_key="unused"),
        openai_api_key="sk-fake",
        model="gpt-fake",
    )
    assert isinstance(provider, OpenAIChatProvider)


def test_build_chat_provider_passes_reasoning_effort_through_to_openai() -> None:
    provider = build_chat_provider(
        "openai",
        openrouter_client=OpenRouterClient(api_key="unused"),
        openai_api_key="sk-fake",
        model="gpt-fake",
        reasoning_effort="high",
    )
    assert isinstance(provider, OpenAIChatProvider)
    assert provider._llm.reasoning_effort == "high"  # noqa: SLF001 - only way to verify passthrough


def test_build_chat_provider_resolves_openrouter_key() -> None:
    provider = build_chat_provider(
        "openrouter",
        openrouter_client=OpenRouterClient(api_key="unused"),
        openai_api_key="",
        model="model-fake",
    )
    assert isinstance(provider, OpenRouterChatProvider)


def test_build_embedding_provider_resolves_openai_key() -> None:
    provider = build_embedding_provider(
        "openai",
        openrouter_client=OpenRouterClient(api_key="unused"),
        openai_api_key="sk-fake",
        model="text-embedding-fake",
    )
    assert isinstance(provider, OpenAIEmbeddingProvider)


def test_build_embedding_provider_resolves_openrouter_key() -> None:
    provider = build_embedding_provider(
        "openrouter",
        openrouter_client=OpenRouterClient(api_key="unused"),
        openai_api_key="",
        model="model-fake",
    )
    assert isinstance(provider, OpenRouterEmbeddingProvider)


def test_build_rerank_provider_resolves_cohere_key() -> None:
    provider = build_rerank_provider(
        "cohere",
        enabled=True,
        openrouter_client=OpenRouterClient(api_key="unused"),
        cohere_client=CohereClient(api_key="unused"),
        model="rerank-fake",
    )
    assert isinstance(provider, CohereRerankProvider)


def test_build_rerank_provider_returns_none_when_disabled() -> None:
    provider = build_rerank_provider(
        "cohere",
        enabled=False,
        openrouter_client=OpenRouterClient(api_key="unused"),
        cohere_client=CohereClient(api_key="unused"),
        model="rerank-fake",
    )
    assert provider is None
