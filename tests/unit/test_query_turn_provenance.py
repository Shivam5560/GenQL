"""What a finished turn says about how it reached its answer.

`to_response` is the only place graph state becomes provenance, so the six
fields are asserted here directly against a state mapping rather than through
a stubbed graph — the CLI's `--verbose` rendering and the HTTP DTO both read
exactly what this mapping produces.

A separate module from `test_query_turn.py` because that file is already at
the project's per-file line cap.

Both shapes matter. A contested turn is the one worth auditing: two
interpretations existed, a probe arbitrated between them, and the answer is
only trustworthy if it can say which won and why. A short-circuited turn
never planned anything, so every field must stay empty rather than reporting
a stale or invented plan.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import initial_state
from genql.api.query_turn import to_response
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate

PLAN = QueryPlan(
    question="how many stores are open",
    plan_text="Count store rows, treating an unset closed date as open.",
    referenced_objects=("local.tpcds.store",),
)
CANDIDATES = (
    SqlCandidate(sql="SELECT count(*) FROM store WHERE s_closed_date_sk IS NULL", plan=PLAN),
    SqlCandidate(sql="SELECT count(*) FROM store", plan=PLAN),
)
PROBE_RESULT = ProbeResult(
    probe=AmbiguityProbe(
        dimension="filter",
        probe_sql="SELECT count(*) FROM tpcds.store WHERE s_closed_date_sk IS NULL",
        candidate_predictions=((0, "7"), (1, "12")),
    ),
    actual_result="7",
    resolved_candidate_index=0,
)
SELECTION = CandidateSelection(
    selected=CANDIDATES[0],
    selected_sql="SELECT count(*) FROM tpcds.store WHERE s_closed_date_sk IS NULL",
    method="probe_resolved",
    rationale="the probe returned 7, which only the open-stores reading predicted",
)


def contested_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("how many stores are open", "local", "t-1"))
    state["intent"] = "analytical_sql"
    state["contested"] = True
    state["plan"] = PLAN
    state["candidates"] = CANDIDATES
    state["validated_sqls"] = (SELECTION.selected_sql, "SELECT count(*) FROM tpcds.store")
    state["probe_results"] = (PROBE_RESULT,)
    state["selection"] = SELECTION
    state["validated_sql"] = SELECTION.selected_sql
    state["result"] = ExecutionResult(
        columns=("count",), rows=((7,),), row_count=1, truncated=False
    )
    return state


def short_circuited_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("hello there", "local", "t-1"))
    state["intent"] = "non_sql"
    return state


def test_a_finished_contested_turn_carries_every_provenance_field() -> None:
    response = to_response("t-1", contested_state())

    assert response.plan_text == PLAN.plan_text
    assert response.referenced_objects == ("local.tpcds.store",)
    assert response.selection_method == "probe_resolved"
    assert response.selection_rationale == SELECTION.rationale
    assert response.candidate_count == 2
    assert response.probe_count == 1


def test_a_short_circuited_turn_carries_no_provenance() -> None:
    """Nothing was planned, generated, probed, or selected, so every field
    must be empty — an inherited default would read as a real plan."""
    response = to_response("t-1", short_circuited_state())

    assert response.plan_text is None
    assert response.referenced_objects == ()
    assert response.selection_method is None
    assert response.selection_rationale is None
    assert response.candidate_count == 0
    assert response.probe_count == 0
