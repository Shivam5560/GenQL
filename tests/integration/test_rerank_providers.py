from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.cohere_client import CohereClient
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.rerank_provider_repository import (
    CohereRerankProvider,
    OpenRouterRerankProvider,
)

_DOCS = ["a fact about apples", "a fact about sales tax", "a fact about oranges"]


@pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)
def test_openrouter_rerank_orders_the_relevant_document_first() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterRerankProvider(client=client, model="cohere/rerank-4-pro")

    scores = provider.rerank("sales tax rate", _DOCS, top_n=3)

    assert scores[0].index == 1


@pytest.mark.skipif(
    not os.environ.get("GENQL_COHERE_API_KEY"), reason="GENQL_COHERE_API_KEY not set"
)
def test_cohere_rerank_orders_the_relevant_document_first() -> None:
    client = CohereClient(api_key=os.environ["GENQL_COHERE_API_KEY"])
    provider = CohereRerankProvider(client=client, model="rerank-v3.5")

    scores = provider.rerank("sales tax rate", _DOCS, top_n=3)

    assert scores[0].index == 1
