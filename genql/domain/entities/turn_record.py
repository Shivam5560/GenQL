"""One rendered turn, written after TurnResponse is known, so a client
re-opening a thread gets exactly what it would have streamed live — without
an adapter that reverse-engineers LangGraph checkpoint state."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_result import ExecutionResult


class TurnRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn_id: str
    thread_id: str
    sequence: int
    question: str
    recap: str | None = None
    validated_sql: str | None = None
    clarifying_question: str | None = None
    result: ExecutionResult | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
    created_at: datetime
