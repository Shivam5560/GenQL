"""Per-stage streaming over the compiled graph.

Split out of query_graph.py to stay under the project's per-file line cap;
`run_query`/`resume_query` are the blocking twins of `stream_query`/
`stream_resume` below, and stay in query_graph.py beside the graph they were
built alongside.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langgraph.types import Command

from genql.api.query_state import initial_state
from genql.domain.errors import UnknownThreadError
from genql.infrastructure.tracing.qa_span import qa_span


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def stream_query(
    graph: Any,
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one mapping per completed node.

    `stream_mode="updates"` gives `{node_name: delta}` after each node, which
    is exactly one SSE event per pipeline stage.
    """
    # The span stays open for the generator's whole life, so the nodes that
    # run between two `next()` calls land inside the turn they belong to.
    with qa_span(question, datasource_name, thread_id) as trace_parent:
        yield from graph.stream(
            initial_state(question, datasource_name, thread_id, domain_id, trace_parent),
            _config(thread_id),
            stream_mode="updates",
        )


def stream_resume(graph: Any, answer: str, thread_id: str) -> Iterator[dict[str, Any]]:
    config = _config(thread_id)
    snapshot = graph.get_state(config)
    if not snapshot.interrupts:
        raise UnknownThreadError(thread_id)
    # Same turn as the one that opened the trace, not a new question — see
    # query_turn.py's resume_turn for why this must join that trace.
    parent = snapshot.values.get("trace_parent") if snapshot.values else None
    with qa_span(answer, None, thread_id, parent=parent):
        yield from graph.stream(Command(resume=answer), config, stream_mode="updates")
