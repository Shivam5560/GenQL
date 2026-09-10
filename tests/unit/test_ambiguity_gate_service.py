"""Stage 2, against a fake ChatProvider and a fake RuleReader: rules suppress a
dimension without a model call, the first low-confidence dimension in
priority order is asked about, an answered dimension is never re-asked, and a
fully covered question skips the model entirely (spec §20)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.entities.ambiguity_assessment import AMBIGUITY_DIMENSIONS
from genql.domain.entities.rule import Rule
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.services.query.ambiguity_gate_service import AmbiguityGateService

T = TypeVar("T", bound=BaseModel)

SPECIFIED = 0.95
VAGUE = 0.10


def rule(name: str, dimension: str) -> Rule:
    return Rule(name=name, dimension=dimension, value="v", description="d")


class FakeRules:
    def __init__(self, rules: Sequence[Rule] = ()) -> None:
        self._rules = tuple(rules)
        self.datasources: list[str] = []

    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        self.datasources.append(datasource_name)
        return self._rules


class FakeChat:
    """Scores SPECIFIED except `vague`, or `scores` verbatim when given."""

    def __init__(
        self,
        vague: Sequence[str] = (),
        question: str = "Which one?",
        scores: dict[str, float] | None = None,
        dimension: str = "",
    ) -> None:
        self.vague = set(vague)
        self.question = question
        self.scores = scores
        self.dimension = dimension
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.calls += 1
        self.prompts.append(prompt)
        scores = self.scores or {
            d: (VAGUE if d in self.vague else SPECIFIED) for d in AMBIGUITY_DIMENSIONS
        }
        return response_schema.model_validate(
            {
                "scores": [{"dimension": d, "confidence": c} for d, c in scores.items()],
                "clarifying_dimension": self.dimension,
                "clarifying_question": self.question,
            }
        )


class RaisingChat:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        raise self.exc


def service(
    chat: object, rules: Sequence[Rule] = (), threshold: float = 0.7
) -> AmbiguityGateService:
    return AmbiguityGateService(chat, FakeRules(rules), threshold)  # type: ignore[arg-type]


def test_a_fully_specified_question_is_not_ambiguous() -> None:
    assessment = service(FakeChat()).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert assessment.missing_dimension is None
    assert assessment.clarifying_question is None


def test_the_first_low_confidence_dimension_in_priority_order_is_the_one_asked_about() -> None:
    chat = FakeChat(vague=("grain", "time_range"), question="Over what time period?")

    assessment = service(chat).assess("show me revenue", "local")

    assert assessment.is_ambiguous is True
    # time_range precedes grain in AMBIGUITY_DIMENSIONS, so it wins.
    assert assessment.missing_dimension == "time_range"
    assert assessment.clarifying_question == "Over what time period?"


def test_only_one_dimension_is_ever_asked_about() -> None:
    chat = FakeChat(vague=("entity", "metric", "time_range", "grain"))

    assessment = service(chat).assess("q", "local")

    assert assessment.missing_dimension == "entity"


def test_a_rule_covering_a_dimension_suppresses_it_and_is_recorded() -> None:
    chat = FakeChat(vague=("time_range",))

    assessment = service(chat, rules=(rule("default_period", "time_range"),)).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert assessment.applied_defaults == (("time_range", "default_period"),)


def test_applied_defaults_are_reported_in_dimension_priority_order() -> None:
    rules = (rule("active_only", "filter"), rule("default_period", "time_range"))

    assessment = service(FakeChat(), rules=rules).assess("q", "local")

    assert assessment.applied_defaults == (
        ("time_range", "default_period"),
        ("filter", "active_only"),
    )


def test_a_rule_naming_an_unknown_dimension_is_ignored_entirely() -> None:
    chat = FakeChat(vague=("time_range",))

    assessment = service(chat, rules=(rule("typo", "time_rnage"),)).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "time_range"
    assert assessment.applied_defaults == ()


def test_the_first_rule_by_name_wins_when_two_claim_one_dimension() -> None:
    rules = (rule("aaa_first", "time_range"), rule("zzz_second", "time_range"))

    assessment = service(FakeChat(), rules=rules).assess("q", "local")

    assert assessment.applied_defaults == (("time_range", "aaa_first"),)


def test_an_already_answered_dimension_is_never_re_asked() -> None:
    chat = FakeChat(vague=("time_range", "grain"))

    assessment = service(chat).assess("q", "local", answers=(("time_range", "last quarter"),))

    assert assessment.missing_dimension == "grain"


def test_the_loop_terminates_after_the_last_open_dimension_is_answered() -> None:
    # The termination proof (spec §9): the sixth dimension answered must end it.
    covered = [d for d in AMBIGUITY_DIMENSIONS if d != "grain"]
    rules = tuple(rule(f"r_{d}", d) for d in covered)
    chat = FakeChat(vague=("grain",), question="At what grain?")
    gate = service(chat, rules=rules)

    first = gate.assess("q", "local")
    assert first.is_ambiguous is True
    assert first.missing_dimension == "grain"

    second = gate.assess("q", "local", answers=(("grain", "by region"),))

    assert second.is_ambiguous is False
    assert second.missing_dimension is None
    assert chat.calls == 1  # no open dimensions left, so no second model call


def test_no_model_call_is_made_when_rules_cover_every_dimension() -> None:
    chat = FakeChat(vague=AMBIGUITY_DIMENSIONS)
    rules = tuple(rule(f"r_{d}", d) for d in AMBIGUITY_DIMENSIONS)

    assessment = service(chat, rules=rules).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert chat.calls == 0
    assert len(assessment.applied_defaults) == len(AMBIGUITY_DIMENSIONS)


def test_a_confidence_exactly_at_the_threshold_counts_as_specified() -> None:
    chat = FakeChat(scores={d: 0.7 for d in AMBIGUITY_DIMENSIONS})

    assessment = service(chat).assess("q", "local")

    assert assessment.is_ambiguous is False


def test_a_dimension_the_model_omitted_is_treated_as_unspecified() -> None:
    chat = FakeChat(scores={"entity": 0.99}, question="Which metric?")

    assessment = service(chat).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "metric"


def test_an_ambiguous_result_with_an_empty_question_is_a_typed_failure() -> None:
    chat = FakeChat(vague=("entity",), question="   ")

    with pytest.raises(AmbiguityGateError):
        service(chat).assess("q", "local")


@pytest.mark.parametrize(
    "exc", [ChatProviderError("502"), ValidationError.from_exception_data("GateResponse", [])]
)
def test_a_provider_or_malformed_response_becomes_an_ambiguity_gate_error(exc: Exception) -> None:
    with pytest.raises(AmbiguityGateError):
        service(RaisingChat(exc)).assess("q", "local")
