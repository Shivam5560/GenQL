"""What the ambiguity gate decided about one question.

The tuple order is the priority order, and it is load-bearing: the gate asks
about the FIRST unresolved dimension, never a batch, per the parent spec's
"raises interrupt() with one targeted question". It is also the termination
argument — every clarifying answer resolves exactly one member of a fixed
six-element tuple, so at most six rounds can occur and no retry counter is
needed.

`applied_defaults` records (dimension, rule_name) rather than
(dimension, value): the response layer needs to tell the user *which rule*
was applied so they can go change it.

`assumed` is the same dimensions as (dimension, VALUE) pairs, plus the
gate's own reading of any dimension it decided not to ask about — every
decision, in short, that the pipeline must apply but the user never stated.
It exists because "the value is one lookup away" (as this docstring used to
claim of `applied_defaults`) turned out to be a lookup nobody performed:
PlanningNode passes `QueryState.clarifications` to the planner, so a rule
default suppressed the clarifying question and then never reached the SQL,
leaving the generator to invent a period of its own — the exact failure
`build_planning_prompt`'s own docstring warns about. A default that does not
reach the planner is worse than no default at all, because it also
suppresses the question that would have caught it.

`suggested_answer` and `options` are what the gate would accept for the
dimension it is asking about, so the UI can offer one keystroke instead of a
typed sentence. Both are best-effort: a provider that returns neither still
yields a perfectly usable question.

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
    suggested_answer: str | None = None
    options: tuple[str, ...] = ()
    applied_defaults: tuple[tuple[str, str], ...] = ()
    assumed: tuple[tuple[str, str], ...] = ()
    dimension_scores: tuple[tuple[str, float], ...] = ()
