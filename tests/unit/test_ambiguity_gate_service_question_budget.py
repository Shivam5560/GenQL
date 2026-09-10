"""The question budget: what the gate does instead of asking, once it is spent.

`max_questions` caps how many clarifying questions ONE turn may ask. Past the
cap the gate stops asking and starts assuming: every remaining
under-threshold dimension is recorded on `assumed` with the model's own best
reading of the question, which the planner is then told to apply. The user
corrects a visible assumption after seeing an answer instead of answering an
interview before seeing one — which is the complaint this answers, a question
against a sales-shaped schema being asked three things in a row before it saw
a single row.

The suggestion half of that fix (`suggested_answer` and `options`, so
accepting the obvious reading costs one keystroke) is proved next door in
test_ambiguity_gate_suggestions.py, which shares this file's fakes. Two files
rather than one to stay under the house file-length limit.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.ambiguity_assessment import AMBIGUITY_DIMENSIONS
from genql.domain.entities.rule import Rule
from genql.services.query.ambiguity_gate_service import AmbiguityGateService
from tests.unit.test_ambiguity_gate_service import SPECIFIED, VAGUE, FakeRules

T = TypeVar("T", bound=BaseModel)


class SuggestingChat:
    """Scores SPECIFIED except `vague`, and always offers an assumption per
    dimension plus a suggestion for the one it asks about."""

    def __init__(
        self,
        vague: Sequence[str] = (),
        question: str = "Which one?",
        dimension: str = "",
        suggested_answer: str = "the most recent complete year",
        options: Sequence[str] = ("last 12 months", "all time"),
    ) -> None:
        self.vague = set(vague)
        self.question = question
        self.dimension = dimension
        self.suggested_answer = suggested_answer
        self.options = tuple(options)
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.calls += 1
        self.prompts.append(prompt)
        return response_schema.model_validate(
            {
                "scores": [
                    {
                        "dimension": d,
                        "confidence": VAGUE if d in self.vague else SPECIFIED,
                        "assumption": f"assumed {d}",
                    }
                    for d in AMBIGUITY_DIMENSIONS
                ],
                "clarifying_dimension": self.dimension,
                "clarifying_question": self.question,
                "suggested_answer": self.suggested_answer,
                "options": list(self.options),
            }
        )


def service(
    chat: object,
    rules: Sequence[Rule] = (),
    threshold: float = 0.7,
    max_questions: int | None = None,
) -> AmbiguityGateService:
    return AmbiguityGateService(
        chat,  # type: ignore[arg-type]
        FakeRules(rules),
        threshold,
        max_questions=max_questions,
    )


# ------------------------------------------------------------ the budget


def test_the_first_question_is_still_asked_at_a_budget_of_one() -> None:
    chat = SuggestingChat(vague=("time_range", "filter"), dimension="time_range")

    assessment = service(chat, max_questions=1).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "time_range"


def test_a_spent_budget_assumes_the_rest_instead_of_asking_again() -> None:
    """The turn that used to ask a second and third question. One dimension
    has been answered, two are still vague — at a budget of 1 the gate
    proceeds, carrying its own reading of both."""
    chat = SuggestingChat(vague=("filter", "comparison_baseline"), dimension="filter")

    assessment = service(chat, max_questions=1).assess(
        "q", "local", answers=(("time_range", "from 2020 to now"),)
    )

    assert assessment.is_ambiguous is False
    assert assessment.clarifying_question is None
    assert assessment.assumed == (
        ("filter", "assumed filter"),
        ("comparison_baseline", "assumed comparison_baseline"),
    )


def test_assumptions_are_reported_in_dimension_priority_order() -> None:
    chat = SuggestingChat(vague=("comparison_baseline", "metric"), dimension="metric")

    assessment = service(chat, max_questions=1).assess("q", "local", answers=(("entity", "x"),))

    assert [dimension for dimension, _ in assessment.assumed] == [
        "metric",
        "comparison_baseline",
    ]


def test_a_confident_dimension_is_never_assumed() -> None:
    """Assumptions cover the gap the gate chose not to ask about, nothing
    else — a dimension the question already specified needs no assumption."""
    chat = SuggestingChat(vague=("filter",), dimension="filter")

    assessment = service(chat, max_questions=1).assess("q", "local", answers=(("entity", "x"),))

    assert assessment.assumed == (("filter", "assumed filter"),)


def test_no_budget_means_the_old_unlimited_behaviour() -> None:
    """`max_questions=None` is every caller written before the budget
    existed: keep asking, one dimension at a time, until nothing is left."""
    chat = SuggestingChat(vague=("filter", "comparison_baseline"), dimension="filter")

    assessment = service(chat).assess("q", "local", answers=(("time_range", "2020"),))

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "filter"
    assert assessment.assumed == ()


def test_a_rule_default_is_carried_as_an_assumption_with_its_value() -> None:
    """The whole point of a YAML default: not merely to suppress the
    question, but to reach the planner as the value to apply. Recording only
    the rule NAME (which `applied_defaults` does, for provenance) left the
    generator to invent its own period anyway."""
    rules = (
        Rule(
            name="default_period",
            dimension="time_range",
            value="the most recent complete calendar year",
            description="d",
        ),
    )

    assessment = service(SuggestingChat(), rules=rules).assess("q", "local")

    assert assessment.applied_defaults == (("time_range", "default_period"),)
    assert assessment.assumed == (("time_range", "the most recent complete calendar year"),)


def test_a_rule_default_reaches_assumed_even_with_no_model_call_at_all() -> None:
    rules = tuple(
        Rule(name=f"r_{d}", dimension=d, value=f"value for {d}", description="d")
        for d in AMBIGUITY_DIMENSIONS
    )
    chat = SuggestingChat(vague=AMBIGUITY_DIMENSIONS)

    assessment = service(chat, rules=rules).assess("q", "local")

    assert chat.calls == 0
    assert len(assessment.assumed) == len(AMBIGUITY_DIMENSIONS)


def test_a_model_assumption_never_overwrites_a_rule_default() -> None:
    """A rule is authored by a human and applies to every question against
    the datasource; a model assumption is a guess about this one. The rule
    wins, and the dimension is not scored at all."""
    rules = (
        Rule(name="default_period", dimension="time_range", value="last year", description="d"),
    )
    chat = SuggestingChat(vague=("time_range", "filter"), dimension="filter")

    assessment = service(chat, rules=rules, max_questions=1).assess(
        "q", "local", answers=(("entity", "x"),)
    )

    assert ("time_range", "last year") in assessment.assumed
    assert ("time_range", "assumed time_range") not in assessment.assumed


def test_a_dimension_the_model_offered_no_assumption_for_is_simply_omitted() -> None:
    """Silence is not a value to apply. The dimension stays unstated rather
    than reaching the planner as an empty string."""

    class SilentChat(SuggestingChat):
        def complete(self, prompt: str, response_schema: type[T]) -> T:
            self.calls += 1
            return response_schema.model_validate(
                {
                    "scores": [{"dimension": d, "confidence": VAGUE} for d in ("filter",)],
                    "clarifying_dimension": "filter",
                    "clarifying_question": "Which filter?",
                }
            )

    assessment = service(SilentChat(), max_questions=1).assess(
        "q", "local", answers=(("entity", "x"),)
    )

    assert assessment.is_ambiguous is False
    assert assessment.assumed == ()
