"""One ablation's results over the whole golden set.

`accuracy` returns 0.0 on an empty report rather than raising: an empty
fixture directory is a configuration mistake, and crashing inside a reporting
property would lose a run that had already finished its work. The CLI prints
counts beside every accuracy, so `0.0 (0/0)` is unmistakable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.golden_outcome import GoldenOutcome


class GoldenRunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ablation_name: str
    outcomes: tuple[GoldenOutcome, ...]

    @property
    def passed_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def accuracy(self) -> float:
        if not self.outcomes:
            return 0.0
        return self.passed_count / len(self.outcomes)

    def counts_for(self, failure_class: str) -> tuple[int, int]:
        matching = [o for o in self.outcomes if o.failure_class == failure_class]
        return sum(1 for o in matching if o.passed), len(matching)
