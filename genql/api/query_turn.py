"""One turn, start to finish or start to pause.

This is where the graph's raw output mapping becomes a typed TurnResponse, and
it is the only place that knows an interrupted invoke returns a
`__interrupt__` key rather than raising. Keeping that knowledge in one file
means a langgraph release that changed the convention breaks here, once.

The lock wraps the invoke, not the whole command, and it is a `with` block so
release survives an exception, an interrupt, and a clean finish alike — one
thread, one in-flight turn, per the parent spec's §13.

A thread id is generated when the caller does not supply one, because even a
turn that finishes without pausing needs one for a follow-up to attach to.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from genql.api.query_graph import resume_query, run_query
from genql.api.query_state import QueryState
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.thread_lock import ThreadLockFactory


def new_thread_id() -> str:
    return f"t-{uuid.uuid4().hex}"


def _applied_defaults(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ambiguity = raw.get("ambiguity")
    if ambiguity is None:
        return ()
    # Tupled rather than passed through: a checkpoint round-trip can restore
    # the pairs as JSON arrays, and TurnResponse declares tuples.
    return tuple((dimension, rule) for dimension, rule in ambiguity.applied_defaults)


def _to_response(thread_id: str, raw: dict[str, Any]) -> TurnResponse:
    interrupts = raw.get("__interrupt__") or ()
    if interrupts:
        return TurnResponse(
            thread_id=thread_id,
            clarifying_question=str(interrupts[0].value),
            applied_defaults=_applied_defaults(raw),
        )
    state = cast(QueryState, raw)
    # An intent is reported only when it stopped the turn. On a finished
    # analytical turn it would be noise beside the rows.
    short_circuited = state["validated_sql"] is None and state["result"] is None
    return TurnResponse(
        thread_id=thread_id,
        intent=state["intent"] if short_circuited else None,
        validated_sql=state["validated_sql"],
        result=state["result"],
        applied_defaults=_applied_defaults(raw),
    )


def start_turn(  # noqa: PLR0913, PLR0917 - mirrors the graph's own start parameters
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
) -> TurnResponse:
    resolved = thread_id or new_thread_id()
    with locks.for_thread(resolved):
        raw = run_query(graph, question, datasource_name, resolved, domain_id)
    return _to_response(resolved, raw)


def resume_turn(graph: Any, locks: ThreadLockFactory, answer: str, thread_id: str) -> TurnResponse:
    with locks.for_thread(thread_id):
        raw = resume_query(graph, answer, thread_id)
    return _to_response(thread_id, raw)
