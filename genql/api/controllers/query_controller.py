"""Two routes, no logic. DTO in, service call, DTO out — every failure is
translated by the app's single exception handler, so there is no `try` here."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container
from genql.api.dtos.query_dtos import ResumeTurnRequest, StartTurnRequest, TurnResponseDto
from genql.api.query_turn import resume_turn, start_turn

router = APIRouter(tags=["queries"])


@router.post("/queries", response_model=TurnResponseDto)
def start(
    request: StartTurnRequest,
    container: Annotated[Any, Depends(get_container)],
) -> TurnResponseDto:
    response = start_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.question,
        request.datasource,
        request.domain_id,
        request.thread_id,
    )
    return TurnResponseDto.from_domain(response)


@router.post("/queries/{thread_id}/resume", response_model=TurnResponseDto)
def resume(
    thread_id: str,
    request: ResumeTurnRequest,
    container: Annotated[Any, Depends(get_container)],
) -> TurnResponseDto:
    response = resume_turn(
        container.query_graph(), container.thread_lock_factory(), request.answer, thread_id
    )
    return TurnResponseDto.from_domain(response)
