"""The runner against real data, over the fixtures Phase 7 already validated.

This is the first test in the project whose *result* is a finding rather than
a pass/fail contract, so it asserts mechanics only: every case produces an
outcome, and every outcome names a reason when it failed. It deliberately does
not assert a minimum accuracy — a threshold here would either be so low it
proved nothing or would turn a real regression in the model provider into a
red suite with no code change.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest

from genql.domain.entities.golden_case import GoldenCase
from genql.domain.ports.turn_runner import TurnRunner
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_provider,
    # `real_provider` is a label, not a gate: the skip has to be explicit, the
    # same way every other real-provider module in this suite does it.
    pytest.mark.skipif(
        not os.environ.get("GENQL_OPENROUTER_API_KEY"),
        reason="requires GENQL_OPENROUTER_API_KEY",
    ),
]


def test_every_golden_case_produces_an_outcome(
    golden_runner: GoldenEvaluationService,
    golden_cases: tuple[GoldenCase, ...],
    golden_turn_runner: Callable[[], TurnRunner],
) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    assert len(report.outcomes) == len(golden_cases)
    assert {o.case_id for o in report.outcomes} == {c.case_id for c in golden_cases}


def test_every_failed_case_names_why(
    golden_runner: GoldenEvaluationService,
    golden_cases: tuple[GoldenCase, ...],
    golden_turn_runner: Callable[[], TurnRunner],
) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    for outcome in report.outcomes:
        if not outcome.passed:
            assert outcome.failure_reason


def test_the_report_prints_counts_alongside_accuracy(
    golden_runner: GoldenEvaluationService,
    golden_cases: tuple[GoldenCase, ...],
    golden_turn_runner: Callable[[], TurnRunner],
) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    assert 0.0 <= report.accuracy <= 1.0
    assert report.passed_count <= len(report.outcomes)
