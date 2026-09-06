"""The only tests in this suite that cost money or need network access.
Skipped cleanly, with a printed reason, when no key is configured — that
skip is not a task failure."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


class _Greeting(BaseModel):
    message: str


def test_complete_returns_a_validated_model() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterChatProvider(client=client, model="anthropic/claude-sonnet-5")

    result = provider.complete(
        "Reply with a JSON object with one field, `message`, containing the word hello.",
        _Greeting,
    )

    assert result.message
