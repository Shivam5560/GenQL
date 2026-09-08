"""The online pipeline as a LangGraph StateGraph — the only file in the
project that builds one.

Phase 6 gives it a checkpointer and an interrupt. `checkpointer` is optional
so that a graph can still be built for a test that only cares about routing;
a graph compiled without one cannot pause, and run_query's thread_id is then
inert.

Three conditional edges now. Out of intent_classification: only
`analytical_sql` proceeds, and the other three intents reach END with the
intent recorded — cheap, and it keeps questions the downstream stages were
never designed for away from them. Out of ambiguity_gate: an ambiguous
assessment routes back to ambiguity_gate itself, so the node re-runs after the
resumed answer lands in state. Out of static_validation: Phase 5's retry edge,
unchanged.

The gate self-loop provably terminates without a retry counter. Every pass
either finds nothing left to ask (AMBIGUITY_DIMENSIONS is a fixed six-element
tuple, and a dimension that has been answered or defaulted is never asked
again) or removes exactly one dimension from that set. Phase 5's guardrail loop
needed a counter because guardrail rules do not shrink; this one does.

The graph does not catch or re-wrap — the CLI does.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from genql.api.query_state import QueryState, initial_state
from genql.domain.errors import UnknownThreadError


class NodeFn(Protocol):
    """What `add_node` accepts, stated the way langgraph states it.

    A Protocol rather than `Callable[[QueryState], dict[str, Any]]` because
    langgraph's own node protocol declares its argument by name (`state`), and
    a bare Callable is positional-only, so it does not structurally satisfy
    that protocol. The node classes already name the parameter `state`.
    """

    def __call__(self, state: QueryState) -> dict[str, Any]: ...


INTENT_CLASSIFICATION = "intent_classification"
AMBIGUITY_GATE = "ambiguity_gate"
DOMAIN_SCOPING = "domain_scoping"
SCHEMA_LINKING = "schema_linking"
PLANNING = "planning"
CANDIDATE_GENERATION = "candidate_generation"
STATIC_VALIDATION = "static_validation"
CRITIQUE = "critique"
AMBIGUITY_PROBING = "ambiguity_probing"
CANDIDATE_SELECTION = "candidate_selection"
GUARDED_EXECUTION = "guarded_execution"


def route_after_intent(state: QueryState) -> str:
    """Only analytical_sql proceeds.

    A missing intent routes to END too, not to the gate: that can only happen
    if the classification node was skipped, and continuing into retrieval on an
    unclassified question is exactly what this stage exists to prevent.
    """
    return AMBIGUITY_GATE if state["intent"] == "analytical_sql" else END


def route_after_gate(state: QueryState) -> str:
    """Ambiguous, so re-assess after the answer; otherwise proceed to scoping.

    The loop-back target is ambiguity_gate itself. On re-entry the node sees a
    `clarifications` tuple one pair longer than last time, so the gate has one
    fewer dimension it can ask about.
    """
    ambiguity = state["ambiguity"]
    if ambiguity is not None and ambiguity.is_ambiguous:
        return AMBIGUITY_GATE
    return DOMAIN_SCOPING


def route_after_validation(state: QueryState) -> str:
    """Trivial by design (Deviation 1): StaticValidationNode itself raises
    when no attempt remains, so this is reachable only when it granted a
    retry or produced survivors."""
    return CRITIQUE if state["validated_sqls"] else CANDIDATE_GENERATION


def route_after_critique(state: QueryState) -> str:
    """Trivial by the same reasoning (Deviation 2): CritiqueNode itself
    raises CritiqueError when the escalation budget is already spent, so
    reaching here with every report fatal means it was just granted."""
    reports = state["critique_reports"]
    if reports and all(r.is_fatal for r in reports):
        return CANDIDATE_GENERATION
    return AMBIGUITY_PROBING


# The compiled-graph type's generic parameters change between langgraph minor
# releases, so this boundary is deliberately untyped; `run_query` below
# restores a plain mapping for every caller.
def build_query_graph(  # noqa: PLR0913, PLR0917 - one parameter per pipeline stage
    intent_classification: NodeFn,
    ambiguity_gate: NodeFn,
    domain_scoping: NodeFn,
    schema_linking: NodeFn,
    planning: NodeFn,
    candidate_generation: NodeFn,
    static_validation: NodeFn,
    critique: NodeFn,
    ambiguity_probing: NodeFn,
    candidate_selection: NodeFn,
    guarded_execution: NodeFn,
    *,
    checkpointer: Any = None,
) -> Any:
    graph: StateGraph[QueryState] = StateGraph(QueryState)
    graph.add_node(INTENT_CLASSIFICATION, intent_classification)
    graph.add_node(AMBIGUITY_GATE, ambiguity_gate)
    graph.add_node(DOMAIN_SCOPING, domain_scoping)
    graph.add_node(SCHEMA_LINKING, schema_linking)
    graph.add_node(PLANNING, planning)
    graph.add_node(CANDIDATE_GENERATION, candidate_generation)
    graph.add_node(STATIC_VALIDATION, static_validation)
    graph.add_node(CRITIQUE, critique)
    graph.add_node(AMBIGUITY_PROBING, ambiguity_probing)
    graph.add_node(CANDIDATE_SELECTION, candidate_selection)
    graph.add_node(GUARDED_EXECUTION, guarded_execution)

    graph.add_edge(START, INTENT_CLASSIFICATION)
    graph.add_conditional_edges(
        INTENT_CLASSIFICATION,
        route_after_intent,
        {AMBIGUITY_GATE: AMBIGUITY_GATE, END: END},
    )
    graph.add_conditional_edges(
        AMBIGUITY_GATE,
        route_after_gate,
        {AMBIGUITY_GATE: AMBIGUITY_GATE, DOMAIN_SCOPING: DOMAIN_SCOPING},
    )
    graph.add_edge(DOMAIN_SCOPING, SCHEMA_LINKING)
    graph.add_edge(SCHEMA_LINKING, PLANNING)
    graph.add_edge(PLANNING, CANDIDATE_GENERATION)
    graph.add_edge(CANDIDATE_GENERATION, STATIC_VALIDATION)
    graph.add_conditional_edges(
        STATIC_VALIDATION,
        route_after_validation,
        {CANDIDATE_GENERATION: CANDIDATE_GENERATION, CRITIQUE: CRITIQUE},
    )
    graph.add_conditional_edges(
        CRITIQUE,
        route_after_critique,
        {CANDIDATE_GENERATION: CANDIDATE_GENERATION, AMBIGUITY_PROBING: AMBIGUITY_PROBING},
    )
    graph.add_edge(AMBIGUITY_PROBING, CANDIDATE_SELECTION)
    graph.add_edge(CANDIDATE_SELECTION, GUARDED_EXECUTION)
    graph.add_edge(GUARDED_EXECUTION, END)
    return graph.compile(checkpointer=checkpointer)


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def run_query(
    graph: Any,
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> dict[str, Any]:
    """Start a turn.

    Returns the raw mapping rather than QueryState: an interrupted run carries
    langgraph's own `__interrupt__` key, which is not a QueryState field, and
    typing the return as QueryState would make reading it a lie. query_turn.py
    narrows this into a TurnResponse.
    """
    return cast(
        dict[str, Any],
        graph.invoke(
            initial_state(question, datasource_name, thread_id, domain_id),
            _config(thread_id),
        ),
    )


def resume_query(graph: Any, answer: str, thread_id: str) -> dict[str, Any]:
    """Answer the question a paused turn asked.

    Command(resume=...) hands the value back to the interrupt() call site that
    raised, so the gate node re-runs with the answer in hand. Intent
    classification does not run again — it already ran on the original
    question, and the checkpoint resumes at the paused node, not at START.

    An unknown or expired thread_id has no checkpoint at all, so
    `graph.get_state` comes back with no pending interrupt and langgraph would
    otherwise run the graph from START with an empty state — the first node
    to read a required key raises a bare KeyError. Checked here, once, so
    every caller gets a typed error instead.
    """
    config = _config(thread_id)
    if not graph.get_state(config).interrupts:
        raise UnknownThreadError(thread_id)
    return cast(dict[str, Any], graph.invoke(Command(resume=answer), config))
