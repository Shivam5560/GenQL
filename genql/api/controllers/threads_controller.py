"""Two routes, no logic: list the caller's threads, or read one thread's
full history. Ownership is enforced by ThreadService, which raises
ThreadOwnershipError — translated to 404 by app.py's exception handler, same
as an unknown thread, so a non-owner cannot distinguish the two."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.thread_dtos import ThreadDetailDto, ThreadSummaryDto, TurnRecordDto
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["threads"])


@router.get("/threads", response_model=list[ThreadSummaryDto])
def list_threads(
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[ThreadSummaryDto]:
    summaries = container.thread_service().list_threads(user.user_id)
    return [ThreadSummaryDto.from_domain(summary) for summary in summaries]


@router.get("/threads/{thread_id}", response_model=ThreadDetailDto)
def get_thread(
    thread_id: str,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ThreadDetailDto:
    summary, turns = container.thread_service().get_thread(user.user_id, thread_id)
    return ThreadDetailDto(
        summary=ThreadSummaryDto.from_domain(summary),
        turns=[TurnRecordDto.from_domain(turn) for turn in turns],
    )
