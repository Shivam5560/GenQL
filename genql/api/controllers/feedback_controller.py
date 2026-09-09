"""One route, no logic: build the entity, hand it to the service, return 204.

204 rather than 200: feedback has no representation worth echoing back, and
the client already has the thread_id it just posted against.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from genql.api.deps import get_container
from genql.api.dtos.feedback_dtos import FeedbackRequest
from genql.domain.entities.feedback import Feedback

router = APIRouter(tags=["feedback"])


@router.post("/queries/{thread_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def submit(
    thread_id: str,
    request: FeedbackRequest,
    container: Annotated[Any, Depends(get_container)],
) -> None:
    feedback = Feedback(
        thread_id=thread_id,
        rating=request.rating,
        corrected_sql=request.corrected_sql,
        comment=request.comment,
    )
    container.feedback_service().record(feedback)
