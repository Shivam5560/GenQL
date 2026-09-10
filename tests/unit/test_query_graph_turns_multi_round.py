"""More of Phase 6's graph paths, split out of test_query_graph_turns.py to
stay under the house file-length limit: multi-round termination, independent
threads, resuming an unknown thread, and an explicit domain_id surviving to
schema_linking. Shares the same fake nodes and `generic_interrupt` helper as
test_query_graph_turns.py."""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from genql.api.query_graph import build_query_graph, resume_query, run_query
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.errors import UnknownThreadError
from tests.unit.test_query_graph import (
    LINK,
    RESULT,
    GenerateNode,
    ValidateNode,
    analytical_intent,
    build,
    clear_gate,
    cost_gate_node,
    critique_node,
    execute_node,
    plan_node,
    probing_node,
    selection_node,
    unreached_interrupt,
)
from tests.unit.test_query_graph_turns import CLEAR, generic_interrupt


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
        return {
            "ambiguity": AmbiguityAssessment(
                is_ambiguous=True,
                missing_dimension=dimension,
                clarifying_question=f"Which {dimension}?",
            )
        }

    graph = build(
        ValidateNode(0),
        GenerateNode(),
        gate=gate,
        interrupt_node=generic_interrupt,
        checkpointer=InMemorySaver(),
    )

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
        gate=gate,
        interrupt_node=generic_interrupt,
        checkpointer=InMemorySaver(),
    )

    run_query(graph, "revenue", "local", "t-x")
    run_query(graph, "headcount", "local", "t-y")

    finished = resume_query(graph, "last quarter", "t-x")

    assert finished["question"] == "revenue"


def test_resuming_a_thread_with_no_checkpoint_raises_a_typed_error() -> None:
    """A thread id nobody paused has no interrupt to resume — resume_query
    must refuse rather than let the graph run from START with empty state."""
    graph = build(
        ValidateNode(0),
        GenerateNode(),
        gate=clear_gate,
        interrupt_node=unreached_interrupt,
        checkpointer=InMemorySaver(),
    )

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
        unreached_interrupt,
        lambda state: {},
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

    run_query(graph, "q", "local", "t-domain", domain_id=42)

    assert seen == [42]
