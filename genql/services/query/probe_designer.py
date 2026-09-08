"""Designs the queries that let real warehouse data arbitrate between
candidates that critique could not fully rank. Only designs them — validating
and executing probe_sql is AmbiguityProbingService's job, one layer up, reusing
StaticValidationService and GuardedExecutionService unchanged.

Per Deviation 7, a ChatProviderError from the model call is not wrapped here;
it propagates as-is.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider


class PredictionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    prediction: str


class ProbeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    probe_sql: str
    candidate_predictions: tuple[PredictionResponse, ...] = ()


class ProbeBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    probes: tuple[ProbeResponse, ...]


def build_probe_prompt(
    plan: QueryPlan,
    candidates: tuple[SqlCandidate, ...],
    validated_sqls: tuple[str, ...],
    critiques: tuple[CritiqueReport, ...],
) -> str:
    rendered_candidates = "\n\n".join(
        f"Candidate {i}:\n{sql}" for i, sql in enumerate(validated_sqls)
    )
    rendered_critiques = "\n".join(
        f"Candidate {r.candidate_index}: score={r.score}, defects={[d.message for d in r.defects]}"
        for r in critiques
    )
    return "\n\n".join(
        [
            "The candidates below disagree on how to answer the question. "
            "Design one targeted, read-only PostgreSQL query per contested "
            "dimension whose result would let the REAL DATA decide which "
            "candidate's interpretation is correct.",
            f"Question:\n{plan.question}",
            f"Plan:\n{plan.plan_text}",
            f"Candidates:\n{rendered_candidates}",
            f"Critique findings:\n{rendered_critiques or 'none'}",
            (
                "Rules:\n"
                "- Each probe_sql is a single SELECT with an explicit LIMIT, "
                "referencing only objects the candidates themselves "
                "reference.\n"
                "- For each probe, predict what each candidate's "
                "interpretation implies the probe will return, rendered as "
                "a short string, in `candidate_predictions`.\n"
                "- Return `probes`; an empty list is valid if nothing would "
                "usefully discriminate between the candidates."
            ),
        ]
    )


class LlmProbeDesigner:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]:
        prompt = build_probe_prompt(plan, candidates, validated_sqls, critiques)
        response = self._chat.complete(prompt, ProbeBatchResponse)
        return tuple(
            AmbiguityProbe(
                dimension=p.dimension,
                probe_sql=p.probe_sql,
                candidate_predictions=tuple(
                    (pr.candidate_index, pr.prediction) for pr in p.candidate_predictions
                ),
            )
            for p in response.probes
        )
