"""Six entities. The behaviour worth testing is GoldenRunReport's arithmetic:
every number the ablation harness reports comes out of it, an empty report is
reachable (a fixture directory with no cases), and a ZeroDivisionError in a
reporting property would crash a run that had already done all its work."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.feedback import Feedback
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_outcome import GoldenOutcome
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.entities.stage_event import StageEvent


def _outcome(case_id: str, passed: bool, failure_class: str = "ambiguous_intent") -> GoldenOutcome:
    return GoldenOutcome(
        case_id=case_id,
        failure_class=failure_class,
        passed=passed,
        generated_sql="SELECT 1" if passed else None,
        failure_reason=None if passed else "result mismatch",
        elapsed_ms=10.0,
    )


def test_a_golden_case_carries_its_reference_sql_and_failure_class() -> None:
    case = GoldenCase(
        case_id="c1",
        question="how many customers",
        datasource_name="local",
        reference_sql="SELECT count(*) FROM tpcds.customer",
        failure_class="ambiguous_intent",
    )

    assert case.domain_id is None
    assert case.reference_sql.startswith("SELECT")


def test_a_golden_case_rejects_an_unknown_failure_class() -> None:
    with pytest.raises(ValidationError):
        GoldenCase(
            case_id="c1",
            question="q",
            datasource_name="local",
            reference_sql="SELECT 1",
            failure_class="made_up",
        )


def test_an_empty_report_has_zero_accuracy_and_does_not_divide_by_zero() -> None:
    report = GoldenRunReport(ablation_name="full", outcomes=())

    assert report.accuracy == 0.0
    assert report.passed_count == 0


def test_accuracy_is_passed_over_total() -> None:
    report = GoldenRunReport(
        ablation_name="full",
        outcomes=(_outcome("a", True), _outcome("b", True), _outcome("c", False)),
    )

    assert report.passed_count == 2
    assert report.accuracy == pytest.approx(2 / 3)


def test_counts_for_a_failure_class_returns_passed_and_total() -> None:
    report = GoldenRunReport(
        ablation_name="full",
        outcomes=(
            _outcome("a", True, "ambiguous_intent"),
            _outcome("b", False, "ambiguous_intent"),
            _outcome("c", True, "context_sensitivity"),
        ),
    )

    assert report.counts_for("ambiguous_intent") == (1, 2)
    assert report.counts_for("context_sensitivity") == (1, 1)
    assert report.counts_for("nothing_here") == (0, 0)


def test_an_ablation_carries_its_overrides_and_recompile_flag() -> None:
    ablation = Ablation(
        name="no_domains",
        description="disables domain scoping",
        setting_overrides=(("domain_scoping_enabled", False),),
    )

    assert ablation.requires_recompile is False
    assert ablation.setting_overrides == (("domain_scoping_enabled", False),)


def test_the_baseline_ablation_overrides_nothing() -> None:
    assert Ablation(name="full", description="baseline").setting_overrides == ()


def test_feedback_rejects_a_rating_that_is_not_good_or_bad() -> None:
    with pytest.raises(ValidationError):
        Feedback(thread_id="t-1", rating="meh")


def test_feedback_may_carry_a_correction() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="SELECT 2")

    assert feedback.corrected_sql == "SELECT 2"


def test_a_stage_event_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        StageEvent(stage="planning", status="thinking")


def test_a_stage_event_carries_an_optional_detail_line() -> None:
    assert StageEvent(stage="planning", status="completed").detail is None
