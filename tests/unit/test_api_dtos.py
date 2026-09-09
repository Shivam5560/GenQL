"""The DTO is the wire contract Phase 9's frontend will be written against, so
the mapping from the domain entity is pinned here rather than left implicit.

`rows` becomes a list of lists because JSON has no tuples, and a client that
round-trips the payload must get the same shape back."""

from __future__ import annotations

from genql.api.dtos.query_dtos import TurnResponseDto
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_response import TurnResponse


def test_a_finished_turn_maps_its_rows_and_columns() -> None:
    response = TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT 1",
        result=ExecutionResult(columns=("n",), rows=((1,), (2,)), row_count=2, truncated=False),
    )

    dto = TurnResponseDto.from_domain(response)

    assert dto.columns == ["n"]
    assert dto.rows == [[1], [2]]
    assert dto.row_count == 2
    assert dto.truncated is False


def test_a_paused_turn_carries_its_question_and_no_rows() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(thread_id="t-1", clarifying_question="which quarter?")
    )

    assert dto.clarifying_question == "which quarter?"
    assert dto.rows == []
    assert dto.row_count == 0


def test_an_over_budget_turn_carries_its_suggestion_and_the_declined_sql() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(
            thread_id="t-1", validated_sql="SELECT 1", narrowing_suggestion="too expensive"
        )
    )

    assert dto.narrowing_suggestion == "too expensive"
    assert dto.validated_sql == "SELECT 1"
    assert dto.rows == []


def test_applied_defaults_become_a_list_of_pairs() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(thread_id="t-1", applied_defaults=(("time_range", "fiscal_year"),))
    )

    assert dto.applied_defaults == [["time_range", "fiscal_year"]]
