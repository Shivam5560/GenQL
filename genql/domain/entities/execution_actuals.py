"""What `EXPLAIN (ANALYZE, BUFFERS)` measured, as opposed to what
`EXPLAIN (FORMAT JSON)` predicted.

Its own entity rather than four fields on RewriteOutcome because the
repository that reads it does not know which rewrite produced the statement —
it reads a plan and reports numbers, and RewriteOutcomeRecordingService is
what joins those numbers to the rules that were applied.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutionActuals(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_time_ms: float
    rows: int
    shared_buffers_hit: int
    shared_buffers_read: int
