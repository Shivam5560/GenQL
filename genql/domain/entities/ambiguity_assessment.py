"""What the ambiguity gate decided about one question.

The tuple order is the priority order, and it is load-bearing: the gate asks
about the FIRST unresolved dimension, never a batch, per the parent spec's
"raises interrupt() with one targeted question". It is also the termination
argument — every clarifying answer resolves exactly one member of a fixed
six-element tuple, so at most six rounds can occur and no retry counter is
needed.

`applied_defaults` records (dimension, rule_name) rather than
(dimension, value): the response layer needs to tell the user *which rule*
was applied so they can go change it, and the value is one lookup away.

`dimension_scores` carries forward every per-dimension confidence the gate
has ever measured for this question, merging in whatever the caller already
knew (QueryState.gate_scores) with whatever this call freshly scored. The
caller persists it and passes it back on the next round so
AmbiguityGateService never re-asks the model to re-confirm a dimension it
already scored confidently — only the question text changes round to round,
not which dimensions still need judging.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

AMBIGUITY_DIMENSIONS: tuple[str, ...] = (
    "entity",
    "metric",
    "time_range",
    "grain",
    "filter",
    "comparison_baseline",
)


class AmbiguityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_ambiguous: bool
    missing_dimension: str | None = None
    clarifying_question: str | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
    dimension_scores: tuple[tuple[str, float], ...] = ()
