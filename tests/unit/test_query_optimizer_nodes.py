"""The gate node and the recorder hook on GuardedExecutionNode.

The property that matters most is the last one: a recorder that explodes must
not fail a turn whose query already returned rows. Recording is a diagnostic,
and a diagnostic that can break a successful answer is worse than no
diagnostic."""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_nodes import GuardedExecutionNode
from genql.api.query_optimizer_nodes import RewriteAndCostGateNode
from genql.api.query_state import initial_state
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import OptimizationError

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1", plan=PLAN)
SELECTION = CandidateSelection(
    selected=CANDIDATE,
    selected_sql="SELECT id FROM shop.orders",
    method="single_survivor",
    rationale="r",
)
RESULT = ExecutionResult(columns=("id",), rows=((1,),), row_count=1, truncated=False)


def _state(**overrides: Any) -> Any:
    state = initial_state("q", "local", "t-1")
    state["plan"] = PLAN
    state["links"] = (SchemaLink(object_qualified_name="local.shop.orders"),)
    state["selection"] = SELECTION
    state["validated_sql"] = SELECTION.selected_sql
    state.update(overrides)
    return state


class _Service:
    def __init__(self, result: OptimizationResult) -> None:
        self.result = result
        self.calls = 0

    def optimize(self, plan, sql, links, datasource_name):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.result


def test_the_gate_writes_the_optimization_result_and_the_rewritten_sql() -> None:
    service = _Service(
        OptimizationResult(
            sql="SELECT id FROM shop.orders LIMIT 100",
            rules_applied=("projection_pruning",),
            estimated_cost=10.0,
            within_budget=True,
        )
    )

    delta = RewriteAndCostGateNode(service).__call__(_state())

    assert delta["validated_sql"] == "SELECT id FROM shop.orders LIMIT 100"
    assert delta["optimization"].rules_applied == ("projection_pruning",)


def test_an_over_budget_gate_still_reports_the_sql_it_declined_to_run() -> None:
    service = _Service(
        OptimizationResult(
            sql="SELECT id FROM shop.orders",
            estimated_cost=900_000.0,
            within_budget=False,
            narrowing_suggestion="too big",
        )
    )

    delta = RewriteAndCostGateNode(service).__call__(_state())

    assert delta["validated_sql"] == "SELECT id FROM shop.orders"
    assert delta["optimization"].within_budget is False


def test_the_gate_reached_without_a_selection_raises() -> None:
    service = _Service(OptimizationResult(sql="SELECT 1", estimated_cost=1.0, within_budget=True))

    with pytest.raises(OptimizationError):
        RewriteAndCostGateNode(service).__call__(_state(selection=None))


def test_the_gate_reached_without_a_plan_raises() -> None:
    service = _Service(OptimizationResult(sql="SELECT 1", estimated_cost=1.0, within_budget=True))

    with pytest.raises(OptimizationError):
        RewriteAndCostGateNode(service).__call__(_state(plan=None))


class _Execution:
    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        return RESULT


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], float, str]] = []

    def record(self, sql, rules_applied, estimated_cost, datasource_name):  # type: ignore[no-untyped-def]
        self.calls.append((sql, rules_applied, estimated_cost, datasource_name))


class _ExplodingRecorder:
    def record(self, sql, rules_applied, estimated_cost, datasource_name):  # type: ignore[no-untyped-def]
        raise RuntimeError("explain analyze failed")


def _executed_state() -> Any:
    return _state(
        optimization=OptimizationResult(
            sql="SELECT id FROM shop.orders",
            rules_applied=("predicate_pushdown",),
            estimated_cost=42.0,
            within_budget=True,
        )
    )


def test_guarded_execution_without_a_recorder_behaves_exactly_as_before() -> None:
    delta = GuardedExecutionNode(_Execution()).__call__(_executed_state())

    assert delta["result"] == RESULT


def test_guarded_execution_with_a_recorder_records_what_actually_ran() -> None:
    recorder = _Recorder()

    GuardedExecutionNode(_Execution(), recorder=recorder).__call__(_executed_state())

    assert recorder.calls == [
        ("SELECT id FROM shop.orders", ("predicate_pushdown",), 42.0, "local")
    ]


def test_a_recorder_that_raises_never_fails_a_successful_turn() -> None:
    delta = GuardedExecutionNode(_Execution(), recorder=_ExplodingRecorder()).__call__(
        _executed_state()
    )

    assert delta["result"] == RESULT


def test_a_recorder_is_not_called_when_the_turn_carried_no_optimization() -> None:
    """Defensive: the recorder needs the estimate and the rules, and a state
    with no optimization has neither."""
    recorder = _Recorder()

    GuardedExecutionNode(_Execution(), recorder=recorder).__call__(_state())

    assert recorder.calls == []
