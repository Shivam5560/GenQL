"""GET, not POST, because the browser EventSource API cannot issue a POST and
the first client for this route is Phase 9's frontend.

`iterate_in_threadpool` is what bridges the synchronous generator into the
event loop. It costs one worker thread for the duration of a turn — documented
in the spec's risks, and acceptable for the single-user target.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from genql.api.deps import get_container, get_current_user
from genql.api.sse.event_stream import stage_event_stream
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["queries"])


@router.get("/queries/stream")
def stream(  # noqa: PLR0913, PLR0917 - one query parameter per turn input
    question: str,
    datasource: str,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    domain_id: int | None = None,
    thread_id: str | None = None,
    answer: str | None = None,
) -> EventSourceResponse:
    generator = stage_event_stream(
        container.query_graph(),
        container.thread_lock_factory(),
        question,
        datasource,
        domain_id,
        thread_id,
        answer,
    )
    return EventSourceResponse(iterate_in_threadpool(generator))
