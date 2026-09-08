"""The wiring, proven with fake nodes so no ChatProvider, database, or
retriever is involved. Candidates are tuples throughout — the non-contested
path is just the len == 1 case, matching the real StaticValidationNode/
CandidateSelectionNode's own shape.

Phase 6 prepends three stages and Phase 6.5 three more; the paths they add
live in tests/unit/test_query_graph_turns.py rather than here — together the
two sets do not fit under the project's per-file line cap. The fake nodes and
the `build` helper below are shared with that file.

ValidateNode raises StaticValidationError itself once no attempt remains,
mirroring the real StaticValidationNode's Deviation-1 behaviour — since
route_after_validation is raise-free, only the node itself can prove the
graph does not loop forever on an exhausted retry.
"""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_graph import (
    build_query_graph,
    route_after_critique,
    route_after_validation,
    run_query,
)
from genql.api.query_state import initial_state
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
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
    return {"ambiguity": CLEAR, "contested": False}


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
            "candidates": (CANDIDATE,),
            "retry_count": state["retry_count"] + (1 if state["violations"] else 0),
        }


class ValidateNode:
    """Fails its first `failures` invocations, then succeeds. Raises
    StaticValidationError itself once no attempt remains (Deviation 1) —
    route_after_validation is raise-free, so only the node proves the graph
    does not loop forever."""

    def __init__(self, failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS):
        self.remaining = failures
        self.violations = violations

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.remaining > 0:
            self.remaining -= 1
            repairable = any(v.repairable for v in self.violations)
            if not (repairable and state["retry_count"] == 0):
                raise StaticValidationError(self.violations)
            return {"candidates": (), "validated_sqls": (), "violations": self.violations}
        return {
            "candidates": (CANDIDATE,),
            "validated_sqls": ("SELECT 1 LIMIT 1",),
            "violations": (),
        }


def critique_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"critique_reports": ()}


def probing_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"probe_results": ()}


def selection_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection": None,
        "validated_sql": state["validated_sqls"][0] if state["validated_sqls"] else None,
    }


def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"result": RESULT}


def build(  # noqa: PLR0913, PLR0917 - one parameter per overridable stage
    validate: Any,
    generate: Any,
    intent: Any = analytical_intent,
    gate: Any = clear_gate,
    scope: Any = no_scope,
    critique: Any = critique_node,
    probing: Any = probing_node,
    selection: Any = selection_node,
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
        critique,
        probing,
        selection,
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


def test_the_router_sends_a_validated_batch_to_critique() -> None:
    state = initial_state("q", "local", "t-1")
    state["validated_sqls"] = ("SELECT 1 LIMIT 1",)

    assert route_after_validation(state) == "critique"


def test_the_router_sends_no_survivors_back_to_generation() -> None:
    state = initial_state("q", "local", "t-1")

    assert route_after_validation(state) == "candidate_generation"


def test_route_after_critique_sends_a_non_fatal_batch_onward() -> None:
    state = initial_state("q", "local", "t-1")
    state["critique_reports"] = (CritiqueReport(candidate_index=0, defects=(), score=0.9),)

    assert route_after_critique(state) == "ambiguity_probing"


def test_route_after_critique_sends_a_just_escalated_all_fatal_batch_back() -> None:
    state = initial_state("q", "local", "t-1")
    state["critique_reports"] = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.1,
        ),
    )

    assert route_after_critique(state) == "candidate_generation"


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
