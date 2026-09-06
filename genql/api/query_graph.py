"""The online pipeline as a LangGraph StateGraph — the only file in Phase 5
that imports langgraph.

No checkpointer and no interrupt(). The parent spec's §13 ties both
specifically to multi-turn clarification, which does not exist yet, so each
invocation here is a single stateless run from question to answer. Building a
real graph now is a deliberate bet: Phase 6 extends this graph rather than
migrating a plain function pipeline into one under more time pressure.

One conditional edge, out of static_validation. Success goes to execution; a
first repairable failure goes back to candidate_generation with the violations
attached; anything else raises. The graph does not catch or re-wrap — the CLI
does.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from langgraph.graph import END, START, StateGraph

from genql.api.query_state import QueryState, initial_state
from genql.domain.errors import StaticValidationError


class NodeFn(Protocol):
    """What `add_node` accepts, stated the way langgraph states it.

    A Protocol rather than `Callable[[QueryState], dict[str, Any]]` because
    langgraph's own node protocol declares its argument by name (`state`), and
    a bare Callable is positional-only, so it does not structurally satisfy
    that protocol. The five node classes already name the parameter `state`.
    """

    def __call__(self, state: QueryState) -> dict[str, Any]: ...


SCHEMA_LINKING = "schema_linking"
PLANNING = "planning"
CANDIDATE_GENERATION = "candidate_generation"
STATIC_VALIDATION = "static_validation"
GUARDED_EXECUTION = "guarded_execution"


def route_after_validation(state: QueryState) -> str:
    """Success, one retry, or raise — the whole loop-termination argument.

    Repairability is checked as well as the retry budget, per the spec's
    "repairable-but-still-failing violation with retry_count == 0". A rule that
    declared its own violation unrepairable has already had its one repair
    attempt refused inside StaticValidationService, so regenerating against the
    same plan and links would spend a model call to be told the same thing.
    """
    if state["validated_sql"] is not None:
        return GUARDED_EXECUTION
    repairable = any(violation.repairable for violation in state["violations"])
    if repairable and state["retry_count"] == 0:
        return CANDIDATE_GENERATION
    raise StaticValidationError(state["violations"])


# The compiled-graph type's generic parameters change between langgraph minor
# releases, so this boundary is deliberately untyped; `run_query` below
# restores QueryState for every caller.
def build_query_graph(
    schema_linking: NodeFn,
    planning: NodeFn,
    candidate_generation: NodeFn,
    static_validation: NodeFn,
    guarded_execution: NodeFn,
) -> Any:
    graph: StateGraph[QueryState] = StateGraph(QueryState)
    graph.add_node(SCHEMA_LINKING, schema_linking)
    graph.add_node(PLANNING, planning)
    graph.add_node(CANDIDATE_GENERATION, candidate_generation)
    graph.add_node(STATIC_VALIDATION, static_validation)
    graph.add_node(GUARDED_EXECUTION, guarded_execution)

    graph.add_edge(START, SCHEMA_LINKING)
    graph.add_edge(SCHEMA_LINKING, PLANNING)
    graph.add_edge(PLANNING, CANDIDATE_GENERATION)
    graph.add_edge(CANDIDATE_GENERATION, STATIC_VALIDATION)
    graph.add_conditional_edges(
        STATIC_VALIDATION,
        route_after_validation,
        {
            CANDIDATE_GENERATION: CANDIDATE_GENERATION,
            GUARDED_EXECUTION: GUARDED_EXECUTION,
        },
    )
    graph.add_edge(GUARDED_EXECUTION, END)
    return graph.compile()


def run_query(
    graph: Any, question: str, datasource_name: str, domain_id: int | None = None
) -> QueryState:
    return cast(QueryState, graph.invoke(initial_state(question, datasource_name, domain_id)))
