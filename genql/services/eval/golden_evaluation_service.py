"""Runs the golden set and reports what happened, case by case.

Nothing here raises for a case-level problem. A run over fifty cases that
aborts on case three has measured nothing, and the four ways a turn can end
without rows — paused, short-circuited, over budget, failed — are all just
"this case did not produce the expected result", each with its own reason
string so the report says which.

The reference statement runs through the same GuardedExecutionService as the
generated one, so both sides share a row cap. That makes a truncated reference
a fixture error rather than a verdict: truncation is order-dependent, so two
truncated result sets are not comparable even when the underlying queries
agree.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_outcome import GoldenOutcome
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import GenqlError
from genql.domain.ports.turn_runner import TurnRunner
from genql.services.eval.result_comparator import ResultComparator
from genql.services.query.guarded_execution_service import GuardedExecutionService


class GoldenEvaluationService:
    def __init__(self, execution: GuardedExecutionService, comparator: ResultComparator) -> None:
        self._execution = execution
        self._comparator = comparator

    def run(
        self, ablation_name: str, cases: Sequence[GoldenCase], runner: TurnRunner
    ) -> GoldenRunReport:
        return GoldenRunReport(
            ablation_name=ablation_name,
            outcomes=tuple(self._run_case(case, runner) for case in cases),
        )

    def _run_case(self, case: GoldenCase, runner: TurnRunner) -> GoldenOutcome:
        started = time.perf_counter()
        try:
            expected = self._execution.execute(case.reference_sql, case.datasource_name)
        except GenqlError as exc:
            return self._failed(case, started, None, f"reference SQL failed: {exc}")
        if expected.truncated:
            return self._failed(
                case,
                started,
                None,
                "reference result exceeds the row cap — narrow the fixture",
            )

        try:
            response = runner.run(case.question, case.datasource_name, case.domain_id)
        except GenqlError as exc:
            return self._failed(case, started, None, str(exc))

        reason = _why_no_result(response)
        if reason is not None:
            return self._failed(case, started, response.validated_sql, reason)

        assert response.result is not None  # guaranteed by _why_no_result
        matched, mismatch = self._comparator.compare(expected, response.result)
        return GoldenOutcome(
            case_id=case.case_id,
            failure_class=case.failure_class,
            passed=matched,
            generated_sql=response.validated_sql,
            failure_reason=None if matched else mismatch,
            elapsed_ms=_elapsed(started),
        )

    @staticmethod
    def _failed(case: GoldenCase, started: float, sql: str | None, reason: str) -> GoldenOutcome:
        return GoldenOutcome(
            case_id=case.case_id,
            failure_class=case.failure_class,
            passed=False,
            generated_sql=sql,
            failure_reason=reason,
            elapsed_ms=_elapsed(started),
        )


def _elapsed(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


def _why_no_result(response: TurnResponse) -> str | None:
    """The four ways a turn ends without rows, each named for the report."""
    if response.clarifying_question is not None:
        return f"paused for clarification: {response.clarifying_question}"
    if response.narrowing_suggestion is not None:
        return f"stopped by the cost budget: {response.narrowing_suggestion}"
    if response.intent is not None:
        return f"short-circuited as a {response.intent} question"
    if response.result is None:
        return "the turn produced no result"
    return None
