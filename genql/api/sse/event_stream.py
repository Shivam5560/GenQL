"""The generator behind GET /v1/queries/stream.

Three guarantees a client depends on, in this order: one `stage` event per
completed pipeline node; exactly one terminal event, which is always `result`,
`clarification`, or `error`; and nothing after the terminal event. A stream
that just stops is indistinguishable from a dropped connection, which is why
even a failure is delivered as an event rather than as a closed socket.

The deltas are accumulated into a merged state as they pass, so the terminal
event can be built by the same `to_response` the blocking path uses. Without
that, the streaming and blocking endpoints could report a turn differently.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from genql.api.dtos.query_dtos import TurnResponseDto
from genql.api.query_state import initial_state
from genql.api.query_stream import stream_query, stream_resume
from genql.api.query_turn import new_thread_id, to_response
from genql.api.sse.stage_events import to_stage_event
from genql.domain.errors import GenqlError
from genql.domain.ports.thread_lock import ThreadLockFactory


def _event(name: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload, default=str)}


def _terminal(thread_id: str, merged: dict[str, Any]) -> dict[str, str]:
    response = to_response(thread_id, merged)
    payload = TurnResponseDto.from_domain(response).model_dump()
    if response.clarifying_question is not None:
        return _event("clarification", payload)
    return _event("result", payload)


def stage_event_stream(  # noqa: PLR0913, PLR0917 - mirrors the graph's start parameters
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
    answer: str | None = None,
) -> Iterator[dict[str, str]]:
    resolved = thread_id or new_thread_id()
    merged: dict[str, Any] = dict(initial_state(question, datasource_name, resolved, domain_id))
    try:
        with locks.for_thread(resolved):
            chunks = (
                stream_resume(graph, answer, resolved)
                if answer is not None
                else stream_query(graph, question, datasource_name, resolved, domain_id)
            )
            for chunk in chunks:
                for node, delta in chunk.items():
                    if isinstance(delta, dict):
                        merged.update(delta)
                    else:
                        merged["__interrupt__"] = delta
                    yield _event("stage", to_stage_event(node, delta).model_dump())
    except GenqlError as exc:
        yield _event("error", {"error": type(exc).__name__, "detail": str(exc)})
        return

    yield _terminal(resolved, merged)
