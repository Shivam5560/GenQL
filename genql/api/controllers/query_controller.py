"""Two routes, no logic. DTO in, service call, DTO out — every failure is
translated by the app's single exception handler, so there is no `try` here."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.query_dtos import ResumeTurnRequest, StartTurnRequest, TurnResponseDto
from genql.api.query_turn import resume_turn, start_turn
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["queries"])


@router.post("/queries", response_model=TurnResponseDto)
def start(
    request: StartTurnRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> TurnResponseDto:
    response = start_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.question,
        request.datasource,
        request.domain_id,
        request.thread_id,
        user_id=user.user_id,
        threads=container.thread_repository(),
        turn_records=container.turn_record_repository(),
    )
    return TurnResponseDto.from_domain(response)


@router.post("/queries/{thread_id}/resume", response_model=TurnResponseDto)
def resume(
    thread_id: str,
    request: ResumeTurnRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> TurnResponseDto:
    response = resume_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.answer,
        thread_id,
        user_id=user.user_id,
        threads=container.thread_repository(),
        turn_records=container.turn_record_repository(),
    )
    return TurnResponseDto.from_domain(response)
