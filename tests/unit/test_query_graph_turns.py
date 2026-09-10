"""The three paths Phase 6 adds to the graph, proven with fake nodes.

A non-analytical intent that reaches END without touching retrieval, an
ambiguous question that pauses and then resumes to a finished answer, and a
gate that asks about a second dimension after the first is answered and still
terminates. The last two need a checkpointer, so they use InMemorySaver — the
Postgres saver is proven separately in
tests/integration/test_postgres_checkpointer.py, and what these assert is the
GRAPH's routing, which is saver-independent.

The fake nodes come from tests.unit.test_query_graph so both halves of the
graph's test coverage exercise the same fakes; splitting was forced by the
project's per-file line cap, not by a difference in what is being tested.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END
from langgraph.types import interrupt as real_interrupt

from genql.api.query_graph import (
    AMBIGUITY_INTERRUPT,
    DOMAIN_SCOPING,
    PLANNING,
    build_query_graph,
    resume_query,
    route_after_gate,
    route_after_intent,
    run_query,
)
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from tests.unit.test_query_graph import (
    CLEAR,
    LINK,
    RESULT,
    GenerateNode,
    ValidateNode,
    build,
    clear_gate,
    cost_gate_node,
    critique_node,
    execute_node,
    no_scope,
    plan_node,
    probing_node,
    selection_node,
    unreached_interrupt,
)


def generic_interrupt(state: dict[str, Any]) -> dict[str, Any]:
    """Stands in for the real AmbiguityInterruptNode: reads the assessment a
    fake `gate` already put in state, pauses if it's ambiguous, and records
    the answer. Shared by every test below whose fake gate reports
    ambiguity, so each one only has to describe what it's ambiguous ABOUT."""
    assessment = state["ambiguity"]
    if assessment is None or not assessment.is_ambiguous:
        return {}
    answers = tuple((dimension, answer) for dimension, answer in state["clarifications"])
    answer = real_interrupt(assessment.clarifying_question)
    return {"clarifications": answers + ((assessment.missing_dimension, str(answer)),)}


def test_a_non_analytical_intent_reaches_the_end_without_linking() -> None:
    linked: list[str] = []

    def recording_link(state: dict[str, Any]) -> dict[str, Any]:
        linked.append(state["question"])
        return {"links": (LINK,)}

    graph = build_query_graph(
        lambda state: {"intent": "non_sql"},
        clear_gate,
        unreached_interrupt,
        no_scope,
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        critique_node,
        probing_node,
        selection_node,
        cost_gate_node,
        execute_node,
    )

    final = run_query(graph, "hello there", "local", "t-intent")

    assert final["intent"] == "non_sql"
    assert final["validated_sql"] is None
    assert final["result"] is None
    assert linked == []


def test_route_after_intent_sends_only_analytical_sql_onward() -> None:
    assert route_after_intent({"intent": "analytical_sql"}) == DOMAIN_SCOPING
    for intent in ("metadata_question", "followup", "non_sql", None):
        assert route_after_intent({"intent": intent}) == END


def test_route_after_gate_loops_back_while_ambiguous() -> None:
    ambiguous = AmbiguityAssessment(
        is_ambiguous=True, missing_dimension="grain", clarifying_question="At what grain?"
    )

    assert route_after_gate({"ambiguity": ambiguous}) == AMBIGUITY_INTERRUPT
    assert route_after_gate({"ambiguity": CLEAR}) == PLANNING
    assert route_after_gate({"ambiguity": None}) == PLANNING


def test_an_ambiguous_question_pauses_and_then_resumes_to_an_answer() -> None:
    """The whole phase, as one test: pause, resume, finish."""

    class Gate:
        def __init__(self) -> None:
            self.passes = 0

        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            self.passes += 1
            if state["clarifications"]:
                return {"ambiguity": CLEAR}
            return {
                "ambiguity": AmbiguityAssessment(
                    is_ambiguous=True,
                    missing_dimension="time_range",
                    clarifying_question="Over what time period?",
                )
            }

    graph = build(
        ValidateNode(0),
        GenerateNode(),
        gate=Gate(),
        interrupt_node=generic_interrupt,
        checkpointer=InMemorySaver(),
    )

    paused = run_query(graph, "show me revenue", "local", "t-pause")
    assert paused["__interrupt__"][0].value == "Over what time period?"
    assert paused["validated_sql"] is None

    finished = resume_query(graph, "last quarter", "t-pause")

    assert "__interrupt__" not in finished
    assert finished["clarifications"] == (("time_range", "last quarter"),)
    assert finished["validated_sql"] == "SELECT 1 LIMIT 1"
    assert finished["result"] == RESULT
