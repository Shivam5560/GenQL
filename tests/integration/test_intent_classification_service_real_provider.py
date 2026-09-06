"""One real classification against a live model, skipped cleanly without a key.

Two questions, not one: a passing test that only ever sees analytical_sql
would also pass against a service hardcoded to return it. The negative case is
what proves the prompt actually discriminates.
"""

from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.intent_classification_service import IntentClassificationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


@pytest.fixture()
def service() -> IntentClassificationService:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return IntentClassificationService(provider)


def test_a_counting_question_classifies_as_analytical_sql(
    service: IntentClassificationService,
) -> None:
    assert service.classify("how many stores did we open last quarter") == "analytical_sql"


def test_a_greeting_does_not_classify_as_analytical_sql(
    service: IntentClassificationService,
) -> None:
    assert service.classify("hey there, how are you doing today") != "analytical_sql"
