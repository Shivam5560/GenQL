"""The DTO is the wire contract Phase 9's frontend will be written against, so
the mapping from the domain entity is pinned here rather than left implicit.

`rows` becomes a list of lists because JSON has no tuples, and a client that
round-trips the payload must get the same shape back."""

from __future__ import annotations

from datetime import UTC, datetime

from genql.api.dtos.query_dtos import TurnResponseDto
from genql.api.dtos.thread_dtos import TurnRecordDto
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.stage_event import StageEvent
from genql.domain.entities.turn_record import TurnRecord
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


def _record(stages: tuple[StageEvent, ...]) -> TurnRecord:
    return TurnRecord(
        turn_id="tr-1",
        thread_id="t-1",
        sequence=0,
        question="how many customers",
        stages=stages,
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )


def test_a_recorded_turn_carries_its_stage_trail_in_order() -> None:
    """What GET /threads/{id} hands the rail: the same three fields the live
    SSE `stage` event ships, in the order the stages happened."""
    dto = TurnRecordDto.from_domain(
        _record(
            (
                StageEvent(stage="schema_linking", status="completed", detail="10 objects linked"),
                StageEvent(stage="candidate_selection", status="completed", detail=None),
            )
        )
    )

    assert [(s.stage, s.status, s.detail) for s in dto.stages] == [
        ("schema_linking", "completed", "10 objects linked"),
        ("candidate_selection", "completed", None),
    ]


def test_a_turn_with_no_recorded_trail_serialises_an_empty_list() -> None:
    """A pre-migration row, or one asked through the blocking endpoint. The
    client reads this as "no discussion recorded", not as an error."""
    assert TurnRecordDto.from_domain(_record(())).stages == []
