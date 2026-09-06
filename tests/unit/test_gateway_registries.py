"""The three gateway registries exist and are populated once the package is
imported — mirrors test_graph_registries.py."""

from __future__ import annotations

import genql.repositories.gateway  # noqa: F401 - registration side effect
from genql.repositories.gateway.registry import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    RERANK_PROVIDERS,
)


def test_the_three_registries_are_distinct_and_populated() -> None:
    assert CHAT_PROVIDERS.name == "chat_providers"
    assert EMBEDDING_PROVIDERS.name == "embedding_providers"
    assert RERANK_PROVIDERS.name == "rerank_providers"
    assert "openrouter" in CHAT_PROVIDERS.keys()  # noqa: SIM118 - .keys() returns a list, not a dict
    assert "openrouter" in EMBEDDING_PROVIDERS.keys()  # noqa: SIM118
    assert {"openrouter", "cohere"} <= set(RERANK_PROVIDERS.keys())
