"""Six new entities. `CritiqueReport.is_fatal` is the one behaviour worth
testing directly: CritiqueNode and CandidateSelectionService both call it, and
a typo in the severity comparison would silently make every candidate look
non-fatal or every one fatal."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)


def test_a_defect_carries_a_dimension_severity_and_message() -> None:
    defect = Defect(dimension="time_range", severity="fatal", message="bad join")

    assert defect.severity == "fatal"


def test_a_defect_dimension_may_be_none_for_a_non_ambiguity_defect() -> None:
    defect = Defect(dimension=None, severity="advisory", message="style nit")

    assert defect.dimension is None


def test_a_defect_is_frozen() -> None:
    defect = Defect(dimension=None, severity="advisory", message="m")

    with pytest.raises(ValidationError):
        defect.message = "other"


def test_a_critique_report_with_a_fatal_defect_is_fatal() -> None:
    report = CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="fatal", message="bad join"),),
        score=0.2,
    )

    assert report.is_fatal is True


def test_a_critique_report_with_only_advisory_defects_is_not_fatal() -> None:
    report = CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="advisory", message="style nit"),),
        score=0.9,
    )

    assert report.is_fatal is False


def test_a_critique_report_with_no_defects_is_not_fatal() -> None:
    report = CritiqueReport(candidate_index=0, defects=(), score=1.0)

    assert report.is_fatal is False


def test_an_ambiguity_probe_carries_a_prediction_per_candidate() -> None:
    probe = AmbiguityProbe(
        dimension="grain",
        probe_sql="SELECT count(*) FROM shop.orders LIMIT 1",
        candidate_predictions=((0, "12"), (1, "144")),
    )

    assert probe.candidate_predictions == ((0, "12"), (1, "144"))


def test_a_probe_result_names_which_candidate_it_resolved() -> None:
    probe = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())
    result = ProbeResult(probe=probe, actual_result="12", resolved_candidate_index=0)

    assert result.resolved_candidate_index == 0


def test_a_probe_result_may_resolve_nothing() -> None:
    probe = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())
    result = ProbeResult(probe=probe, actual_result="99", resolved_candidate_index=None)

    assert result.resolved_candidate_index is None


def test_a_candidate_selection_carries_the_qualified_sql_and_the_method() -> None:
    selection = CandidateSelection(
        selected=CANDIDATE,
        selected_sql="SELECT 1 FROM local.shop.orders LIMIT 1",
        method="single_survivor",
        rationale="only one candidate survived validation",
    )

    assert selection.method == "single_survivor"
    assert selection.selected_sql != selection.selected.sql


def test_a_candidate_selection_rejects_an_unknown_method() -> None:
    with pytest.raises(ValidationError):
        CandidateSelection(
            selected=CANDIDATE, selected_sql="SELECT 1", method="guessed", rationale="r"
        )


def test_an_ambiguity_example_carries_alternative_interpretations() -> None:
    example = AmbiguityExample(
        question="show me revenue",
        interpretations=("gross revenue", "net revenue"),
        resolution="Unqualified revenue means net revenue per the finance glossary.",
        domain_id=3,
    )

    assert example.interpretations == ("gross revenue", "net revenue")
    assert example.domain_id == 3


def test_an_ambiguity_example_domain_id_may_be_none() -> None:
    example = AmbiguityExample(
        question="q", interpretations=("a", "b"), resolution="r", domain_id=None
    )

    assert example.domain_id is None
