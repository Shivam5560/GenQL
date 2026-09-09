"""What the rewrite-and-cost-gate stage decided about one statement.

`within_budget` and `narrowing_suggestion` are validated against each other
rather than left independent: the graph routes on the first and the CLI prints
the second, so a result where they disagree either prints an empty explanation
to the user or executes a query the gate meant to stop.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    rules_applied: tuple[str, ...] = ()
    estimated_cost: float
    within_budget: bool
    narrowing_suggestion: str | None = None

    @model_validator(mode="after")
    def _suggestion_matches_verdict(self) -> Self:
        if self.within_budget and self.narrowing_suggestion is not None:
            raise ValueError("a within-budget result must not carry a narrowing suggestion")
        if not self.within_budget and self.narrowing_suggestion is None:
            raise ValueError("an over-budget result must carry a narrowing suggestion")
        return self
