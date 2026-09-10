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

from pydantic import ValidationError

from genql.domain.entities.ambiguity_assessment import (
    AMBIGUITY_DIMENSIONS,
    AmbiguityAssessment,
)
from genql.domain.entities.rule import Rule
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.rule_reader import RuleReader
from genql.services.query.ambiguity_gate_prompt import GateResponse, build_gate_prompt
from genql.services.query.schema_time_dimension import has_time_dimension


class AmbiguityGateService:
    def __init__(
        self,
        chat: ChatProvider,
        rules: RuleReader,
        threshold: float,
        max_questions: int | None = None,
    ) -> None:
        self._chat = chat
        self._rules = rules
        self._threshold = threshold
        self._max_questions = max_questions

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
            (dimension, defaults[dimension].name)
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension in defaults
        )
        # The rule VALUES, which is what the planner needs; `applied` above
        # carries the rule NAMES, which is what the user needs in order to go
        # change one. Assumptions the model supplies for dimensions the
        # budget suppressed are appended to this further down, never in front
        # of it: a human-authored rule outranks a guess about one question.
        assumed = tuple(
            (dimension, defaults[dimension].value)
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
        schema_excluded = {"time_range"} if links and not has_time_dimension(links) else set()
        open_dimensions = tuple(
            dimension
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension not in defaults
            and dimension not in answered
            and dimension not in schema_excluded
        )
        if not open_dimensions:
            return AmbiguityAssessment(
                is_ambiguous=False, applied_defaults=applied, assumed=assumed
            )

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
                is_ambiguous=False,
                applied_defaults=applied,
                assumed=assumed,
                dimension_scores=dimension_scores,
            )
        # The question budget. Every answer in `answers` is one question this
        # turn already asked, so a spent budget means stop asking and start
        # assuming: each still-under-threshold dimension is carried on
        # `assumed` with the model's own reading of it, which PlanningNode
        # then states to the planner as binding.
        #
        # This is the fix for the interview problem. The termination proof was
        # always sound — six dimensions, one resolved per round, so at most
        # six rounds — but "terminates" is not "acceptable": a question
        # against a sales-shaped schema really was asked about time_range,
        # then filter, then comparison_baseline before it saw a row, and each
        # round costs a full round trip plus a human. Assuming and showing
        # the assumption lets the user correct one visible decision after
        # seeing an answer, instead of answering an interview before seeing
        # one. `None` disables the budget entirely, which is every caller
        # written before it existed.
        if self._max_questions is not None and len(answers) >= self._max_questions:
            # `under` non-empty implies every one of its members was scored on
            # this call (see the assert below for the full argument), so the
            # assumptions are all present in `response`.
            assert response is not None
            assumptions = {
                score.dimension: score.assumption.strip()
                for score in response.scores
                if score.assumption.strip()
            }
            guesses = tuple(
                (dimension, assumptions[dimension])
                for dimension in under
                if dimension in assumptions
            )
            return AmbiguityAssessment(
                is_ambiguous=False,
                applied_defaults=applied,
                assumed=assumed + guesses,
                dimension_scores=dimension_scores,
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
        suggested = response.suggested_answer.strip()
        return AmbiguityAssessment(
            is_ambiguous=True,
            missing_dimension=missing,
            clarifying_question=clarifying_question,
            # Blank rather than absent is the same thing to a caller deciding
            # whether to render a chip, so it is normalised to None here
            # instead of at every read site.
            suggested_answer=suggested or None,
            options=tuple(option.strip() for option in response.options if option.strip()),
            applied_defaults=applied,
            assumed=assumed,
            dimension_scores=dimension_scores,
        )

    def _defaults(self, datasource_name: str) -> dict[str, Rule]:
        """First rule by name wins per dimension; the reader orders by name, so
        the winner is stable rather than dependent on row order. A rule naming
        a dimension outside AMBIGUITY_DIMENSIONS is inert, per the spec's §11.

        The whole Rule is kept, not just its name: callers need the name for
        provenance and the value to actually apply."""
        defaults: dict[str, Rule] = {}
        for rule in self._rules.read_rules(datasource_name):
            if rule.dimension in AMBIGUITY_DIMENSIONS and rule.dimension not in defaults:
                defaults[rule.dimension] = rule
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
