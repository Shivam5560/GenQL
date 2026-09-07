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
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.rule_reader import RuleReader


class DimensionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    confidence: float


class GateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scores: tuple[DimensionScore, ...]
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
        "- Return `clarifying_question`: a single, specific question you would "
        "ask about the LOWEST-confidence dimension. Ask about one thing. Never "
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
    ) -> AmbiguityAssessment:
        defaults = self._defaults(datasource_name)
        applied = tuple(
            (dimension, defaults[dimension])
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension in defaults
        )
        answered = {dimension for dimension, _ in answers}
        open_dimensions = tuple(
            dimension
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension not in defaults and dimension not in answered
        )
        if not open_dimensions:
            return AmbiguityAssessment(is_ambiguous=False, applied_defaults=applied)

        response = self._score(question, open_dimensions, answers)
        scored = {score.dimension: score.confidence for score in response.scores}
        missing = next(
            (
                dimension
                for dimension in open_dimensions
                # A dimension the model omitted scores 0.0: silence is not
                # evidence that the question specified it.
                if scored.get(dimension, 0.0) < self._threshold
            ),
            None,
        )
        if missing is None:
            return AmbiguityAssessment(is_ambiguous=False, applied_defaults=applied)
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
