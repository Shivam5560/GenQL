from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.embedding_provider_repository import OpenRouterEmbeddingProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


def test_embed_returns_one_vector_per_text() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterEmbeddingProvider(client=client, model="openai/text-embedding-3-small")

    vectors = provider.embed(["point-of-sale line items", "customer demographics"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1536
