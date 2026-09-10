"""Stage 2 of the parent spec's §9: decide whether to ask, and if so, ask about
exactly one thing.

Three decisions are worth stating.

First, rules are applied BEFORE the model call, not after it. A dimension a
YAML rule covers is not a question the user should ever see, so it never
reaches the prompt, and if rules cover everything the model is not called at
all. That is the §20 demand-driven cost rule applied to the gate itself: a
well-specified question against a well-ruled datasource pays nothing here.

Second, one question, never a batch. The parent spec asks for "one targeted
question", so the first dimension below threshold in AMBIGUITY_DIMENSIONS order
wins and the rest wait for the next pass.

Third, this terminates without a retry counter. `open_dimensions` is
AMBIGUITY_DIMENSIONS minus the rule-covered ones minus the already-answered
ones; the caller appends the answered dimension to `answers` before the next
pass, so the set strictly shrinks and is empty after at most six rounds. Phase
5's guardrail loop needed a counter because its rule set does not shrink; this
one does.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.ambiguity_assessment import (
    AMBIGUITY_DIMENSIONS,
    AmbiguityAssessment,
)
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.rule_reader import RuleReader

# Substrings that mark a column as date/time-shaped. SchemaLink carries no
# type information (genql.domain.entities.schema_link), only names, so this is
# a naming heuristic rather than a type check — good enough to tell "nothing
# in scope could possibly answer a time_range question" from "maybe it could",
# which is all this filter needs.
_DATE_COLUMN_MARKERS = ("date", "_dt", "_yr", "year", "month", "quarter", "_dow")

# Dimension-table bookkeeping columns — TPC-DS's `s_rec_start_date` /
# `s_rec_end_date` (SCD2 row-validity tracking, present on every dimension
# table that carries history) and `s_closed_date_sk` (a one-off lifecycle
# event on the dimension row itself, not a transactional date) — match
# `_DATE_COLUMN_MARKERS` but are not a business date a generic question is
# asking about. Left unexcluded, a question with no real time dimension at
# all ("top 5 states by number of stores" against `tpcds.store`, which
# carries only these) still triggered the clarifying question this filter
# exists to remove. A question specifically about store openings/closures
# would still need to name that explicitly; this filter only decides whether
# to preemptively ask "what time period?" for questions that never asked
# about time at all.
_SCD_BOOKKEEPING_MARKERS = ("rec_start", "rec_end", "closed_date")


def _has_time_dimension(links: tuple[SchemaLink, ...]) -> bool:
    return any(
        marker in name.lower()
        for link in links
        for name in link.column_names
        if not any(scd in name.lower() for scd in _SCD_BOOKKEEPING_MARKERS)
        for marker in _DATE_COLUMN_MARKERS
    )


class DimensionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    confidence: float


class GateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scores: tuple[DimensionScore, ...]
    # Which dimension `clarifying_question` actually asks about. Returned
    # rather than re-derived, because the two must agree: the caller records
    # the user's answer against this dimension and removes it from the open
    # set, so a question about `filter` filed under `time_range` both answers
    # the wrong dimension and permanently closes one that was never asked.
    clarifying_dimension: str
    clarifying_question: str


def build_gate_prompt(
    question: str,
    open_dimensions: tuple[str, ...],
    answers: tuple[tuple[str, str], ...],
) -> str:
    context = "\n".join(f"- {dimension}: {answer}" for dimension, answer in answers) or (
        "- (none yet)"
    )
    dimensions = "\n".join(f"- {dimension}" for dimension in open_dimensions)
    return (
        "You are judging how completely an analytical question specifies what "
        "it wants, so a SQL generator does not have to guess.\n\n"
        f"Question:\n{question}\n\n"
        f"Already clarified by the user:\n{context}\n\n"
        f"Dimensions still to judge:\n{dimensions}\n\n"
        "Rules:\n"
        "- For each dimension listed above, return a `confidence` between 0.0 "
        "and 1.0 that the question (plus the clarifications) already specifies "
        "it well enough to write SQL without guessing.\n"
        "- Judge only the dimensions listed. Do not invent others.\n"
        "- Return `clarifying_dimension`: the LOWEST-confidence dimension, "
        "copied exactly from the list above.\n"
        "- Return `clarifying_question`: a single, specific question about "
        "`clarifying_dimension` and nothing else. Ask about one thing. Never "
        "ask a compound question and never present a form."
    )


class AmbiguityGateService:
    def __init__(self, chat: ChatProvider, rules: RuleReader, threshold: float) -> None:
        self._chat = chat
        self._rules = rules
        self._threshold = threshold

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
        links: tuple[SchemaLink, ...] = (),
        known_scores: tuple[tuple[str, float], ...] = (),
    ) -> AmbiguityAssessment:
        defaults = self._defaults(datasource_name)
        applied = tuple(
            (dimension, defaults[dimension])
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension in defaults
        )
        answered = {dimension for dimension, _ in answers}
        # `time_range` is dropped from the open set, not scored low, when
        # nothing schema_linking found exposes a date/time column: a dimension
        # the schema cannot express is not something the question left
        # ambiguous, it is something no answer could ever narrow. Scoring it
        # and hoping the threshold catches it is exactly the over-triggering
        # this replaces — asking "what time period?" about a row count that
        # has no date column at all.
        schema_excluded = {"time_range"} if links and not _has_time_dimension(links) else set()
        open_dimensions = tuple(
            dimension
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension not in defaults
            and dimension not in answered
            and dimension not in schema_excluded
        )
        if not open_dimensions:
            return AmbiguityAssessment(is_ambiguous=False, applied_defaults=applied)

        known = dict(known_scores)
        # Re-score a dimension only if it has never been judged, or was judged
        # under threshold and therefore still needs a fresh clarifying
        # question — a dimension already known to be confidently specified
        # does not need re-confirming just because a DIFFERENT dimension was
        # answered since. This is what turns the round that finally has
        # nothing left to ask into a free, deterministic check instead of a
        # full model call: `to_score` is empty exactly when every open
        # dimension is already known and confident.
        to_score = tuple(
            dimension
            for dimension in open_dimensions
            if dimension not in known or known[dimension] < self._threshold
        )
        response = None
        if to_score:
            response = self._score(question, to_score, answers)
            for score in response.scores:
                known[score.dimension] = score.confidence
            # A dimension the model omitted scores 0.0: silence is not
            # evidence that the question specified it.
            for dimension in to_score:
                known.setdefault(dimension, 0.0)
        dimension_scores = tuple((d, known[d]) for d in open_dimensions if d in known)

        under = tuple(
            dimension
            for dimension in open_dimensions
            if known.get(dimension, 0.0) < self._threshold
        )
        if not under:
            return AmbiguityAssessment(
                is_ambiguous=False, applied_defaults=applied, dimension_scores=dimension_scores
            )
        # `under` non-empty implies `to_score` was non-empty (every dimension
        # in `under` was either newly scored or already-known-low-and-thus-
        # rescored above), so `response` is never None here.
        assert response is not None  # see comment above: under non-empty implies to_score was too
        # The dimension the question was actually written about wins, so the
        # answer is recorded against what was asked. It is trusted only after
        # being confirmed both open and genuinely under threshold; a model that
        # names something else falls back to priority order, which is the
        # tuple's documented job and keeps the loop shrinking either way.
        missing = (
            response.clarifying_dimension if response.clarifying_dimension in under else under[0]
        )
        clarifying_question = response.clarifying_question.strip()
        if not clarifying_question:
            raise AmbiguityGateError(
                f"the gate found {missing!r} under-specified in {question!r} but "
                "returned no clarifying question to ask"
            )
        return AmbiguityAssessment(
            is_ambiguous=True,
            missing_dimension=missing,
            clarifying_question=clarifying_question,
            applied_defaults=applied,
            dimension_scores=dimension_scores,
        )

    def _defaults(self, datasource_name: str) -> dict[str, str]:
        """First rule by name wins per dimension; the reader orders by name, so
        the winner is stable rather than dependent on row order. A rule naming
        a dimension outside AMBIGUITY_DIMENSIONS is inert, per the spec's §11."""
        defaults: dict[str, str] = {}
        for rule in self._rules.read_rules(datasource_name):
            if rule.dimension in AMBIGUITY_DIMENSIONS and rule.dimension not in defaults:
                defaults[rule.dimension] = rule.name
        return defaults

    def _score(
        self,
        question: str,
        open_dimensions: tuple[str, ...],
        answers: tuple[tuple[str, str], ...],
    ) -> GateResponse:
        try:
            return self._chat.complete(
                build_gate_prompt(question, open_dimensions, answers), GateResponse
            )
        except (ChatProviderError, ValidationError) as exc:
            raise AmbiguityGateError(f"failed to assess {question!r}: {exc}") from exc
