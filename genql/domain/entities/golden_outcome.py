"""What one case did.

`failure_class` is copied from the case rather than looked up, so a report can
group by class without holding the fixtures it came from — the JSON report is
readable on its own, which is the point of writing one.

`passed=False` with a `failure_reason` covers every non-matching outcome: a
paused turn, a short-circuited intent, an over-budget narrowing, a raised
error, and an actual result mismatch. They are all "this case did not produce
the expected rows", and flattening them keeps accuracy meaning one thing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.failure_class import FailureClass


class GoldenOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    failure_class: FailureClass
    passed: bool
    generated_sql: str | None = None
    failure_reason: str | None = None
    elapsed_ms: float
