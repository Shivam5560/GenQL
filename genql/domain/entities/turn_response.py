"""What the CLI prints for one turn: a paused clarification, a short-circuited
non-SQL explanation, or a finished answer.

One DTO rather than three because the CLI's job is the same in all three cases
— print something and exit 0 — and because a paused turn is not an error. The
thread_id is always set: even a turn that finishes in one shot has one, so a
follow-up question can attach to it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_result import ExecutionResult


class TurnResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    clarifying_question: str | None = None
    intent: str | None = None
    validated_sql: str | None = None
    result: ExecutionResult | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
