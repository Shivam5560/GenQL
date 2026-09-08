"""AmbiguityProbingService wraps StaticValidationService and
GuardedExecutionService unchanged, matching Deviation 9: a probe that fails
either is a bug in ProbeDesigner's prompt, and propagates loudly rather than
being silently dropped."""

from __future__ import annotations

import pytest

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ExecutionError, StaticValidationError
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)
PROBE = AmbiguityProbe(
    dimension="grain",
    probe_sql="SELECT count(*) FROM shop.orders LIMIT 1",
    candidate_predictions=((0, "12"), (1, "144")),
)


class FakeDesigner:
    def __init__(self, probes: tuple[AmbiguityProbe, ...]) -> None:
        self._probes = probes

    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]:
        return self._probes


class FakeValidation:
    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        return "SELECT count(*) FROM local.shop.orders LIMIT 1"


class RaisingValidation:
    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        raise StaticValidationError(())


class FakeExecution:
    def __init__(self, row: tuple[object, ...] = (12,)) -> None:
        self._row = row

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        return ExecutionResult(columns=("n",), rows=(self._row,), row_count=1, truncated=False)


class RaisingExecution:
    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        raise ExecutionError("boom")


def test_a_matching_prediction_resolves_its_candidate() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), FakeExecution((12,)), max_probes=3
    )

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert results[0].resolved_candidate_index == 0
    assert results[0].actual_result == "12"


def test_no_matching_prediction_resolves_nothing() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), FakeExecution((999,)), max_probes=3
    )

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert results[0].resolved_candidate_index is None


def test_probes_are_capped_at_max_probes() -> None:
    designer = FakeDesigner((PROBE, PROBE, PROBE, PROBE))
    service = AmbiguityProbingService(designer, FakeValidation(), FakeExecution(), max_probes=2)

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert len(results) == 2


def test_a_bad_probe_sql_propagates_rather_than_being_dropped() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), RaisingValidation(), FakeExecution(), max_probes=3
    )

    with pytest.raises(StaticValidationError):
        service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")


def test_an_execution_failure_propagates() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), RaisingExecution(), max_probes=3
    )

    with pytest.raises(ExecutionError):
        service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")


def test_zero_probes_designed_means_zero_results() -> None:
    service = AmbiguityProbingService(
        FakeDesigner(()), FakeValidation(), FakeExecution(), max_probes=3
    )

    assert service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local") == ()
