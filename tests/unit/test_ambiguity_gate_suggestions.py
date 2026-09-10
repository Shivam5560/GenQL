"""What a question the gate DOES ask carries with it.

The other half of test_ambiguity_gate_service_question_budget.py, which owns
the shared fakes this file imports. A paused turn used to offer a sentence
and an empty box; a `suggested_answer` plus a couple of `options` turns the
common case — "yes, the obvious reading" — into one tap.

Every assertion here is about degrading gracefully as much as about the happy
path: the chips are an affordance, so a provider that returns none of them
must still produce a question worth asking.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from tests.unit.test_ambiguity_gate_service import VAGUE
from tests.unit.test_ambiguity_gate_service_question_budget import SuggestingChat, service

T = TypeVar("T", bound=BaseModel)


def test_a_question_carries_a_suggested_answer_and_options() -> None:
    chat = SuggestingChat(
        vague=("time_range",),
        dimension="time_range",
        suggested_answer="the most recent complete year",
        options=("last 12 months", "all time"),
    )

    assessment = service(chat).assess("q", "local")

    assert assessment.suggested_answer == "the most recent complete year"
    assert assessment.options == ("last 12 months", "all time")


def test_a_model_that_offers_no_suggestion_still_produces_a_usable_question() -> None:
    """The chips are an affordance, not a contract. A provider that returns
    only the question must still pause the turn rather than fail it."""

    class BareChat(SuggestingChat):
        def complete(self, prompt: str, response_schema: type[T]) -> T:
            self.calls += 1
            return response_schema.model_validate(
                {
                    "scores": [{"dimension": "entity", "confidence": VAGUE}],
                    "clarifying_dimension": "entity",
                    "clarifying_question": "Which entity?",
                }
            )

    assessment = service(BareChat()).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.clarifying_question == "Which entity?"
    assert assessment.suggested_answer is None
    assert assessment.options == ()


def test_the_prompt_asks_for_a_suggestion_and_a_per_dimension_assumption() -> None:
    """Both are useless if the prompt never requests them, and a silently
    absent field degrades into "no chips, no assumptions" rather than into
    an error — so the prompt itself is what has to be asserted."""
    chat = SuggestingChat(vague=("entity",), dimension="entity")

    service(chat).assess("q", "local")

    prompt = chat.prompts[0]
    assert "suggested_answer" in prompt
    assert "options" in prompt
    assert "assumption" in prompt


def test_a_blank_suggestion_is_dropped_rather_than_offered_empty() -> None:
    chat = SuggestingChat(vague=("entity",), dimension="entity", suggested_answer="   ")

    assessment = service(chat).assess("q", "local")

    assert assessment.suggested_answer is None
