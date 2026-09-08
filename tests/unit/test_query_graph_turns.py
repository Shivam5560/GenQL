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

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END
from langgraph.types import interrupt as real_interrupt

from genql.api.query_graph import (
    AMBIGUITY_GATE,
    DOMAIN_SCOPING,
    build_query_graph,
    resume_query,
    route_after_gate,
    route_after_intent,
    run_query,
)
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.errors import UnknownThreadError
from tests.unit.test_query_graph import (
    CLEAR,
    LINK,
    RESULT,
    GenerateNode,
    ValidateNode,
    analytical_intent,
    build,
    clear_gate,
    critique_node,
    execute_node,
    no_scope,
    plan_node,
    probing_node,
    selection_node,
)


def test_a_non_analytical_intent_reaches_the_end_without_linking() -> None:
    linked: list[str] = []

    def recording_link(state: dict[str, Any]) -> dict[str, Any]:
        linked.append(state["question"])
        return {"links": (LINK,)}

    graph = build_query_graph(
        lambda state: {"intent": "non_sql"},
        clear_gate,
        no_scope,
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        critique_node,
        probing_node,
        selection_node,
        execute_node,
    )

    final = run_query(graph, "hello there", "local", "t-intent")

    assert final["intent"] == "non_sql"
    assert final["validated_sql"] is None
    assert final["result"] is None
    assert linked == []


def test_route_after_intent_sends_only_analytical_sql_onward() -> None:
    assert route_after_intent({"intent": "analytical_sql"}) == AMBIGUITY_GATE
    for intent in ("metadata_question", "followup", "non_sql", None):
        assert route_after_intent({"intent": intent}) == END


def test_route_after_gate_loops_back_while_ambiguous() -> None:
    ambiguous = AmbiguityAssessment(
        is_ambiguous=True, missing_dimension="grain", clarifying_question="At what grain?"
    )

    assert route_after_gate({"ambiguity": ambiguous}) == AMBIGUITY_GATE
    assert route_after_gate({"ambiguity": CLEAR}) == DOMAIN_SCOPING
    assert route_after_gate({"ambiguity": None}) == DOMAIN_SCOPING


def test_an_ambiguous_question_pauses_and_then_resumes_to_an_answer() -> None:
    """The whole phase, as one test: pause, resume, finish."""

    class Gate:
        def __init__(self) -> None:
            self.passes = 0

        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            self.passes += 1
            if state["clarifications"]:
                return {"ambiguity": CLEAR}
            answer = real_interrupt("Over what time period?")
            return {
                "ambiguity": AmbiguityAssessment(
                    is_ambiguous=True,
                    missing_dimension="time_range",
                    clarifying_question="Over what time period?",
                ),
                "clarifications": (("time_range", str(answer)),),
            }

    graph = build(ValidateNode(0), GenerateNode(), gate=Gate(), checkpointer=InMemorySaver())

    paused = run_query(graph, "show me revenue", "local", "t-pause")
    assert paused["__interrupt__"][0].value == "Over what time period?"
    assert paused["validated_sql"] is None

    finished = resume_query(graph, "last quarter", "t-pause")

    assert "__interrupt__" not in finished
    assert finished["clarifications"] == (("time_range", "last quarter"),)
    assert finished["validated_sql"] == "SELECT 1 LIMIT 1"
    assert finished["result"] == RESULT


def test_two_dimensions_take_two_rounds_and_then_terminate() -> None:
    """The termination claim at the graph level: the loop-back edge does not
    spin, because each answered dimension removes itself from the gate's
    remaining set."""
    remaining = ["entity", "time_range"]

    def gate(state: dict[str, Any]) -> dict[str, Any]:
        # Mirrors AmbiguityGateNode._answers: a checkpoint round-trip hands
        # back lists, and the real node normalises before appending.
        answers = tuple((dimension, answer) for dimension, answer in state["clarifications"])
        answered = {dimension for dimension, _ in answers}
        pending = [d for d in remaining if d not in answered]
        if not pending:
            return {"ambiguity": CLEAR}
        dimension = pending[0]
        answer = real_interrupt(f"Which {dimension}?")
        return {
            "ambiguity": AmbiguityAssessment(
                is_ambiguous=True,
                missing_dimension=dimension,
                clarifying_question=f"Which {dimension}?",
            ),
            "clarifications": answers + ((dimension, str(answer)),),
        }

    graph = build(ValidateNode(0), GenerateNode(), gate=gate, checkpointer=InMemorySaver())

    first = run_query(graph, "revenue", "local", "t-two")
    assert first["__interrupt__"][0].value == "Which entity?"

    second = resume_query(graph, "stores", "t-two")
    assert second["__interrupt__"][0].value == "Which time_range?"

    third = resume_query(graph, "last quarter", "t-two")

    assert "__interrupt__" not in third
    assert third["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )
    assert third["result"] == RESULT


def test_two_threads_pause_independently() -> None:
    def gate(state: dict[str, Any]) -> dict[str, Any]:
        if state["clarifications"]:
            return {"ambiguity": CLEAR}
        answer = real_interrupt("Over what time period?")
        return {
            "ambiguity": CLEAR,
            "clarifications": (("time_range", str(answer)),),
        }

    graph = build(ValidateNode(0), GenerateNode(), gate=gate, checkpointer=InMemorySaver())

    run_query(graph, "revenue", "local", "t-x")
    run_query(graph, "headcount", "local", "t-y")

    finished = resume_query(graph, "last quarter", "t-x")

    assert finished["question"] == "revenue"


def test_resuming_a_thread_with_no_checkpoint_raises_a_typed_error() -> None:
    """A thread id nobody paused has no interrupt to resume — resume_query
    must refuse rather than let the graph run from START with empty state."""
    graph = build(ValidateNode(0), GenerateNode(), gate=clear_gate, checkpointer=InMemorySaver())

    with pytest.raises(UnknownThreadError):
        resume_query(graph, "answer", "t-never-existed")


def test_an_explicit_domain_id_survives_to_schema_linking() -> None:
    seen: list[int | None] = []

    def recording_link(state: dict[str, Any]) -> dict[str, Any]:
        seen.append(state["domain_id"])
        return {"links": (LINK,)}

    graph = build_query_graph(
        analytical_intent,
        clear_gate,
        lambda state: {},
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        critique_node,
        probing_node,
        selection_node,
        execute_node,
    )

    run_query(graph, "q", "local", "t-domain", domain_id=42)

    assert seen == [42]
