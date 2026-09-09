"""The cost gate's routing, and what initial_state starts empty.

Split out of tests/unit/test_query_graph.py for the same reason
test_query_graph_turns.py was: the project's per-file line cap, not a
difference in what is being tested. The fakes and the `build` helper still
live in test_query_graph.py.
"""

from __future__ import annotations

from langgraph.graph import END

from genql.api.query_graph import GUARDED_EXECUTION, route_after_cost_gate
from genql.api.query_state import initial_state
from genql.domain.entities.optimization_result import OptimizationResult


def test_an_over_budget_gate_routes_to_end_not_to_execution() -> None:
    state = initial_state("q", "local", "t-1")
    state["optimization"] = OptimizationResult(
        sql="SELECT 1", estimated_cost=9e9, within_budget=False, narrowing_suggestion="s"
    )

    assert route_after_cost_gate(state) == END


def test_a_within_budget_gate_routes_to_guarded_execution() -> None:
    state = initial_state("q", "local", "t-1")
    state["optimization"] = OptimizationResult(
        sql="SELECT 1", estimated_cost=1.0, within_budget=True
    )

    assert route_after_cost_gate(state) == GUARDED_EXECUTION


def test_the_initial_state_starts_empty_with_no_retries_used() -> None:
    state = initial_state("q", "local", "t-1", domain_id=3)

    assert state["retry_count"] == 0
    assert state["violations"] == ()
    assert state["domain_id"] == 3
    assert state["result"] is None
    assert state["thread_id"] == "t-1"
    assert state["intent"] is None
    assert state["ambiguity"] is None
    assert state["clarifications"] == ()
    assert state["candidates"] == ()
    assert state["validated_sqls"] == ()
    assert state["contested"] is False
    assert state["escalated"] is False
    assert state["critique_reports"] == ()
    assert state["probe_results"] == ()
    assert state["selection"] is None
    assert state["optimization"] is None
