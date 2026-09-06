"""Stage 1, tested against a fake ChatProvider — no network, no database.

The interesting behaviour is not "it returns what the model said". It is the
two guards around that: a model that answers with something outside
QUESTION_INTENTS must fail loudly rather than let an unroutable value reach the
graph's conditional edge, and a provider failure must arrive as
IntentClassificationError rather than as a raw ChatProviderError, so the CLI's
single `except GenqlError` prints one line either way.
"""

from __future__ import annotations

from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.errors import ChatProviderError, IntentClassificationError
from genql.domain.value_objects.question_intent import QUESTION_INTENTS
from genql.services.query.intent_classification_service import (
    IntentClassificationService,
    IntentResponse,
    build_intent_prompt,
)

T = TypeVar("T", bound=BaseModel)


class FakeChat:
    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.prompts.append(prompt)
        return response_schema.model_validate({"intent": self.intent})


class RaisingChat:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        raise self.exc


@pytest.mark.parametrize("intent", QUESTION_INTENTS)
def test_every_known_intent_is_returned_unchanged(intent: str) -> None:
    service = IntentClassificationService(FakeChat(intent))

    assert service.classify("how many stores do we have") == intent


def test_an_unknown_intent_is_a_typed_failure() -> None:
    service = IntentClassificationService(FakeChat("write_me_a_poem"))

    with pytest.raises(IntentClassificationError) as exc:
        service.classify("q")

    assert "write_me_a_poem" in str(exc.value)


def test_a_provider_failure_becomes_an_intent_classification_error() -> None:
    service = IntentClassificationService(RaisingChat(ChatProviderError("502")))

    with pytest.raises(IntentClassificationError):
        service.classify("q")


def test_a_malformed_response_becomes_an_intent_classification_error() -> None:
    service = IntentClassificationService(
        RaisingChat(ValidationError.from_exception_data("IntentResponse", []))
    )

    with pytest.raises(IntentClassificationError):
        service.classify("q")


def test_the_prompt_carries_the_question_and_every_allowed_intent() -> None:
    chat = FakeChat("analytical_sql")

    IntentClassificationService(chat).classify("how many stores do we have")

    prompt = chat.prompts[0]
    assert "how many stores do we have" in prompt
    for intent in QUESTION_INTENTS:
        assert intent in prompt


def test_the_prompt_builder_is_pure() -> None:
    assert build_intent_prompt("q") == build_intent_prompt("q")


def test_the_response_model_is_frozen() -> None:
    response = IntentResponse(intent="analytical_sql")

    with pytest.raises(ValidationError):
        response.intent = "non_sql"
