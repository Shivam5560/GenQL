"""The wire shape of one pipeline stage.

Deliberately identical to what the SSE `stage` event already ships, field for
field: a client that renders a live turn's trail and one read back from history
should not need two readings of the same thing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from genql.domain.entities.stage_event import StageEvent


class StageEventDto(BaseModel):
    stage: str
    status: Literal["completed", "paused", "failed"]
    detail: str | None = None

    @classmethod
    def from_domain(cls, event: StageEvent) -> StageEventDto:
        return cls(stage=event.stage, status=event.status, detail=event.detail)
