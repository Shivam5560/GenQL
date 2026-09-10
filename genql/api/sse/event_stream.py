"""The generator behind GET /v1/queries/stream.

Three guarantees a client depends on, in this order: one `stage` event per
completed pipeline node; exactly one terminal event, which is always `result`,
`clarification`, or `error`; and nothing after the terminal event. A stream
that just stops is indistinguishable from a dropped connection, which is why
even a failure is delivered as an event rather than as a closed socket.

`warning` is the one non-terminal event that is not a `stage`. It says
something went wrong beside the turn — history could not be written — without
claiming the turn failed, so the terminal-event guarantee still holds.

The deltas are accumulated into a merged state as they pass, so the terminal
event can be built by the same `to_response` the blocking path uses. Without
that, the streaming and blocking endpoints could report a turn differently.

For the same reason the finished turn is written to thread history here, with
the same `record_turn` the blocking path calls: a turn the user watched arrive
must still be there when they reload. Recording happens after the graph is
done and before the terminal event, so a client that sees `result` can reload
and find it.

The stage events are collected as they are yielded and recorded with the turn,
for the same reason: the trail the user watched is the explanation of the SQL,
and it is worth nothing if it only exists until the tab is refreshed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from genql.api.dtos.query_dtos import TurnResponseDto
from genql.api.query_state import initial_state
from genql.api.query_stream import stream_query, stream_resume
from genql.api.query_turn import new_thread_id, record_turn, to_response
from genql.api.sse.stage_events import to_stage_event
from genql.domain.entities.stage_event import StageEvent
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import GenqlError
from genql.domain.ports.thread_lock import ThreadLockFactory
from genql.domain.ports.thread_repository import ThreadRepository
from genql.domain.ports.turn_record_repository import TurnRecordRepository


def _event(name: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload, default=str)}


def _terminal(response: TurnResponse) -> dict[str, str]:
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
    *,
    user_id: str | None = None,
    threads: ThreadRepository | None = None,
    turn_records: TurnRecordRepository | None = None,
) -> Iterator[dict[str, str]]:
    resolved = thread_id or new_thread_id()
    merged: dict[str, Any] = dict(initial_state(question, datasource_name, resolved, domain_id))
    # Collected alongside `merged` for the same reason: this is the only place
    # stage events exist, and a trail rebuilt later from checkpoint state would
    # be a different reading of the turn than the one the user watched.
    collected: list[StageEvent] = []
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
                    stage = to_stage_event(node, delta)
                    collected.append(stage)
                    yield _event("stage", stage.model_dump())
    except GenqlError as exc:
        yield _event("error", {"error": type(exc).__name__, "detail": str(exc)})
        return

    response = to_response(resolved, merged)
    if user_id is not None and threads is not None and turn_records is not None:
        # A history write that fails must not swallow a turn the user already
        # watched succeed. It is reported as a `warning` — before the terminal
        # event, never after it — because the turn itself did not fail and the
        # client must still receive its result.
        try:
            record_turn(
                threads,
                turn_records,
                resolved,
                user_id,
                None if answer is not None else datasource_name,
                answer if answer is not None else question,
                response,
                tuple(collected),
            )
        except GenqlError as exc:
            yield _event(
                "warning",
                {"error": type(exc).__name__, "detail": f"this turn was not saved: {exc}"},
            )

    yield _terminal(response)
