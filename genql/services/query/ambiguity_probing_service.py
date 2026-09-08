"""Ambiguity-driven probing: for each designed probe, validate and execute it
exactly like a candidate (reusing StaticValidationService and
GuardedExecutionService unchanged), then compare the real result against every
candidate's rendered prediction — a lookup, not a second judgment call.

Gated by the caller (AmbiguityProbingNode) on candidates actually disagreeing
and capped here at `probing_max_probes`, per the parent spec's §19 risk
mitigation. A probe that fails validation or execution is NOT caught here —
per Deviation 9, that is a bug in ProbeDesigner's prompt, and propagates like
any other stage's failure.
"""

from __future__ import annotations

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.probe_designer import ProbeDesigner
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService


def _render_scalar(result: ExecutionResult) -> str:
    if len(result.rows) == 1 and len(result.rows[0]) == 1:
        return str(result.rows[0][0])
    return str(result.rows)


def _uniquely_predicted_by(probe: AmbiguityProbe, actual: str) -> int | None:
    """The index of the ONE candidate whose prediction matched, or None.

    Requiring uniqueness is the whole point of a probe: a probe several
    candidates predict identically discriminates between none of them, so
    matching it must not resolve in favour of whichever happens to be listed
    first. `None` here is the same "inconclusive" signal a probe nobody
    predicted correctly produces, and CandidateSelectionService already
    falls back to critique ranking on it.
    """
    matches = [idx for idx, prediction in probe.candidate_predictions if prediction == actual]
    if len(matches) != 1:
        return None
    return matches[0]


class AmbiguityProbingService:
    def __init__(
        self,
        designer: ProbeDesigner,
        validation: StaticValidationService,
        execution: GuardedExecutionService,
        max_probes: int,
    ) -> None:
        self._designer = designer
        self._validation = validation
        self._execution = execution
        self._max_probes = max_probes

    def probe(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
        datasource_name: str,
    ) -> tuple[ProbeResult, ...]:
        probes = self._designer.design(plan, candidates, validated_sqls, critiques)
        probes = probes[: self._max_probes]

        results = []
        for probe in probes:
            probe_candidate = SqlCandidate(sql=probe.probe_sql, plan=plan)
            validated_probe_sql = self._validation.validate(probe_candidate, datasource_name)
            execution_result = self._execution.execute(validated_probe_sql, datasource_name)
            actual = _render_scalar(execution_result)
            resolved = _uniquely_predicted_by(probe, actual)
            results.append(
                ProbeResult(probe=probe, actual_result=actual, resolved_candidate_index=resolved)
            )
        return tuple(results)
