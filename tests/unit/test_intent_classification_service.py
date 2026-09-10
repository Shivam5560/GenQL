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
    classify_deterministically,
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

    assert service.classify("tell me about widgets") == intent


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

    IntentClassificationService(chat).classify("tell me about widgets")

    prompt = chat.prompts[0]
    assert "tell me about widgets" in prompt
    for intent in QUESTION_INTENTS:
        assert intent in prompt


def test_the_prompt_builder_is_pure() -> None:
    assert build_intent_prompt("q") == build_intent_prompt("q")


def test_the_response_model_is_frozen() -> None:
    response = IntentResponse(intent="analytical_sql")

    with pytest.raises(ValidationError):
        response.intent = "non_sql"


def test_an_obviously_analytical_question_skips_the_model_entirely() -> None:
    """The whole point of the pre-filter: one fewer sequential provider round
    trip on the common path. A FakeChat that was never called proves it."""
    chat = FakeChat("non_sql")

    assert IntentClassificationService(chat).classify("how many stores do we have") == (
        "analytical_sql"
    )
    assert chat.prompts == []


@pytest.mark.parametrize(
    "question",
    [
        "total sales by state",
        "count the customers",
        "top 5 states by number of stores",
        "what is the average order value",
    ],
)
def test_analytical_shapes_are_settled_without_a_call(question: str) -> None:
    assert classify_deterministically(question) == "analytical_sql"


@pytest.mark.parametrize(
    "question",
    [
        "hello there",
        "what tables do you have",
        "what does ss_ext_sales_price mean",
        "show me that instead",
        "tell me about widgets",
        "which columns are in the store table",
    ],
)
def test_anything_not_plainly_analytical_still_reaches_the_model(question: str) -> None:
    """The pre-filter may only ever conclude analytical_sql. Everything that
    could be one of the three short-circuiting intents defers, so the filter
    can never route a real question away from the pipeline."""
    assert classify_deterministically(question) is None


def test_a_disqualifier_beats_an_analytical_marker() -> None:
    """'how many' plus 'instead' is a followup, not a fresh question, and the
    filter must not claim it."""
    assert classify_deterministically("how many instead of that") is None
