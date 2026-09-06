"""Phase 6's entities are frozen for the same reason Phase 5's are: they cross
node boundaries inside the graph and get checkpointed to Postgres, so a node
mutating one in place would be invisible here and corrupting there.

AMBIGUITY_DIMENSIONS is asserted by exact order, not by set membership: the
gate asks about the FIRST unresolved dimension in this tuple, so reordering it
silently changes which question a user is asked.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ambiguity_assessment import (
    AMBIGUITY_DIMENSIONS,
    AmbiguityAssessment,
)
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.rule import Rule
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.value_objects.question_intent import QUESTION_INTENTS


def test_the_six_ambiguity_dimensions_are_in_priority_order() -> None:
    assert AMBIGUITY_DIMENSIONS == (
        "entity",
        "metric",
        "time_range",
        "grain",
        "filter",
        "comparison_baseline",
    )


def test_the_four_question_intents_are_fixed() -> None:
    assert QUESTION_INTENTS == ("analytical_sql", "metadata_question", "followup", "non_sql")


def test_a_rule_carries_a_dimension_and_a_value() -> None:
    rule = Rule(
        name="default_period",
        dimension="time_range",
        value="fiscal_year_to_date",
        description="Unqualified periods mean the fiscal year to date.",
    )

    assert rule.dimension == "time_range"
    assert rule.value == "fiscal_year_to_date"


def test_a_rule_is_frozen() -> None:
    rule = Rule(name="r", dimension="filter", value="status = 'active'", description="d")

    with pytest.raises(ValidationError):
        rule.value = "other"


def test_a_rule_dimension_is_not_validated_against_the_dimension_list() -> None:
    """A typo'd dimension is silently never applied, not rejected at write time.

    Documented as a known gap in the spec's §11. This test pins the current
    behaviour so that closing the gap later is a deliberate, visible change
    rather than an accident.
    """
    rule = Rule(name="r", dimension="time_rnage", value="v", description="d")

    assert rule.dimension not in AMBIGUITY_DIMENSIONS


def test_an_unambiguous_assessment_names_no_dimension() -> None:
    assessment = AmbiguityAssessment(is_ambiguous=False)

    assert assessment.missing_dimension is None
    assert assessment.clarifying_question is None
    assert assessment.applied_defaults == ()


def test_an_ambiguous_assessment_carries_one_dimension_and_one_question() -> None:
    assessment = AmbiguityAssessment(
        is_ambiguous=True,
        missing_dimension="time_range",
        clarifying_question="Over what time period?",
        applied_defaults=(("filter", "active_only"),),
    )

    assert assessment.missing_dimension == "time_range"
    assert assessment.applied_defaults == (("filter", "active_only"),)


def test_an_assessment_coerces_applied_defaults_to_a_tuple_of_tuples() -> None:
    assessment = AmbiguityAssessment(
        is_ambiguous=False, applied_defaults=[["filter", "active_only"]]
    )

    assert assessment.applied_defaults == (("filter", "active_only"),)


def test_a_paused_turn_response_carries_a_question_and_no_result() -> None:
    response = TurnResponse(thread_id="t-1", clarifying_question="Over what time period?")

    assert response.result is None
    assert response.validated_sql is None
    assert response.intent is None


def test_a_finished_turn_response_carries_sql_and_rows() -> None:
    response = TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT 1 LIMIT 1",
        result=ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False),
        applied_defaults=(("time_range", "default_period"),),
    )

    assert response.clarifying_question is None
    assert response.result is not None
    assert response.result.row_count == 1


def test_a_short_circuited_turn_response_carries_only_an_intent() -> None:
    response = TurnResponse(thread_id="t-1", intent="non_sql")

    assert response.intent == "non_sql"
    assert response.validated_sql is None
    assert response.result is None


def test_a_turn_response_is_frozen() -> None:
    response = TurnResponse(thread_id="t-1", intent="non_sql")

    with pytest.raises(ValidationError):
        response.thread_id = "t-2"
