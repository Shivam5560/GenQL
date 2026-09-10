"""The wire shape of one pipeline stage.

Deliberately identical to what the SSE `stage` event already ships, field for
field: a client that renders a live turn's trail and one read back from history
should not need two readings of the same thing.

`facts` travels as a list of two-element lists, matching `applied_defaults`
everywhere else in this package — JSON has no tuple, and a client that has to
tell a pair from an object for one field only is a client that will get it
wrong for that one field.
"""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.stage_event import StageEvent, StageStatus


class StageEventDto(BaseModel):
    stage: str
    status: StageStatus
    detail: str | None = None
    facts: list[list[str]] = []
    duration_ms: int | None = None
    attempt: int = 1

    @classmethod
    def from_domain(cls, event: StageEvent) -> StageEventDto:
        return cls(
            stage=event.stage,
            status=event.status,
            detail=event.detail,
            facts=[[label, value] for label, value in event.facts],
            duration_ms=event.duration_ms,
            attempt=event.attempt,
        )
