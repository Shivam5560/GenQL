"""The wiring, proven with fake nodes so no ChatProvider, database, or
retriever is involved. Four generation paths matter: clean, exactly one retry,
a second failure that stops rather than looping, and an unrepairable violation
that never spends the retry at all.

Phase 6 prepends three stages, and the paths they add — a short-circuiting
intent, a pause-and-resume, a two-round clarification — live in
tests/unit/test_query_graph_turns.py rather than here, because together the
two sets do not fit under the project's per-file line cap. The fake nodes and
the `build` helper below are shared with that file: it imports them from here
so both halves exercise the same graph in the same way.
"""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_graph import build_query_graph, route_after_validation, run_query
from genql.api.query_state import initial_state
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError

LINK = SchemaLink(object_qualified_name="local.shop.orders")
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)
VIOLATIONS = (GuardrailViolation(rule_name="fake", message="bad", repairable=True),)
UNREPAIRABLE = (GuardrailViolation(rule_name="fake", message="fatal", repairable=False),)
RESULT = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False)
CLEAR = AmbiguityAssessment(is_ambiguous=False)


def analytical_intent(state: dict[str, Any]) -> dict[str, Any]:
    return {"intent": "analytical_sql"}


def clear_gate(state: dict[str, Any]) -> dict[str, Any]:
    return {"ambiguity": CLEAR}


def no_scope(state: dict[str, Any]) -> dict[str, Any]:
    return {"domain_id": None}


def link_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"links": (LINK,)}


def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"plan": PLAN}


class GenerateNode:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {
            "candidate": CANDIDATE,
            "retry_count": state["retry_count"] + (1 if state["violations"] else 0),
        }


class ValidateNode:
    """Fails its first `failures` invocations, then succeeds."""

    def __init__(self, failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS):
        self.remaining = failures
        self.violations = violations

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.remaining > 0:
            self.remaining -= 1
            return {"validated_sql": None, "violations": self.violations}
        return {"validated_sql": "SELECT 1 LIMIT 1", "violations": ()}


def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"result": RESULT}


def build(  # noqa: PLR0913, PLR0917 - one parameter per overridable stage
    validate: Any,
    generate: Any,
    intent: Any = analytical_intent,
    gate: Any = clear_gate,
    scope: Any = no_scope,
    checkpointer: Any = None,
) -> Any:
    """One helper so the graph tests below differ only where they mean to."""
    return build_query_graph(
        intent,
        gate,
        scope,
        link_node,
        plan_node,
        generate,
        validate,
        execute_node,
        checkpointer=checkpointer,
    )


def _graph(
    failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS
) -> tuple[Any, GenerateNode]:
    generate = GenerateNode()
    graph = build(ValidateNode(failures, violations), generate)
    return graph, generate


def test_the_clean_path_generates_once_and_returns_a_result() -> None:
    graph, generate = _graph(failures=0)

    final = run_query(graph, "q", "local", "t-1")

    assert generate.calls == 1
    assert final["retry_count"] == 0
    assert final["result"] == RESULT
    assert final["validated_sql"] == "SELECT 1 LIMIT 1"


def test_one_failure_routes_back_to_generation_exactly_once() -> None:
    graph, generate = _graph(failures=1)

    final = run_query(graph, "q", "local", "t-1")

    assert generate.calls == 2
    assert final["retry_count"] == 1
    assert final["result"] == RESULT


def test_a_second_failure_raises_instead_of_looping() -> None:
    graph, generate = _graph(failures=2)

    with pytest.raises(StaticValidationError, match="bad"):
        run_query(graph, "q", "local", "t-1")

    assert generate.calls == 2


def test_an_unrepairable_violation_raises_without_spending_the_retry() -> None:
    graph, generate = _graph(failures=1, violations=UNREPAIRABLE)

    with pytest.raises(StaticValidationError, match="fatal"):
        run_query(graph, "q", "local", "t-1")

    assert generate.calls == 1


def test_the_router_sends_a_validated_statement_to_execution() -> None:
    state = initial_state("q", "local", "t-1")
    state["validated_sql"] = "SELECT 1 LIMIT 1"

    assert route_after_validation(state) == "guarded_execution"


def test_the_router_sends_a_first_failure_back_to_generation() -> None:
    state = initial_state("q", "local", "t-1")
    state["violations"] = VIOLATIONS

    assert route_after_validation(state) == "candidate_generation"


def test_the_router_raises_on_a_failure_after_the_retry_was_used() -> None:
    state = initial_state("q", "local", "t-1")
    state["violations"] = VIOLATIONS
    state["retry_count"] = 1

    with pytest.raises(StaticValidationError):
        route_after_validation(state)


def test_the_router_does_not_retry_an_unrepairable_violation() -> None:
    state = initial_state("q", "local", "t-1")
    state["violations"] = UNREPAIRABLE

    with pytest.raises(StaticValidationError, match="fatal"):
        route_after_validation(state)


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
