"""One pipeline stage's completion, as an SSE client sees it.

`detail` is one short human line, never the state delta: a stage's delta can
contain the whole schema-link set or every candidate statement, and shipping
that down an event stream would make the transport the widest interface in the
system.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    status: Literal["completed", "paused", "failed"]
    detail: str | None = None
