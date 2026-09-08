"""Pure-function tests, no fakes at all — CandidateSelectionService takes no
ChatProvider, so every branch (probe-resolved, critique-ranked, and
critique-ranked's tie-break) is deterministic given its inputs."""

from __future__ import annotations

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.candidate_selection_service import CandidateSelectionService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())
CANDIDATES = (SqlCandidate(sql="A", plan=PLAN), SqlCandidate(sql="B", plan=PLAN))
SQLS = ("SELECT A", "SELECT B")
PROBE = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())


def _service() -> CandidateSelectionService:
    return CandidateSelectionService()


def test_a_resolving_probe_wins_over_critique_scores() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=1),)

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "probe_resolved"
    assert selection.selected is CANDIDATES[1]
    assert selection.selected_sql == SQLS[1]


def test_no_probe_results_falls_back_to_critique_ranking() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.method == "critique_ranked"
    assert selection.selected is CANDIDATES[0]


def test_disagreeing_probe_results_fall_back_to_critique_ranking() -> None:
    """Every probe must agree on the same candidate to resolve; conflicting
    probes are as inconclusive as none at all."""
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (
        ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=0),
        ProbeResult(probe=PROBE, actual_result="y", resolved_candidate_index=1),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "critique_ranked"


def test_an_unresolved_probe_is_treated_as_inconclusive() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=None),)

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "critique_ranked"


def test_critique_ranking_excludes_fatal_candidates() -> None:
    critiques = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="bad join"),),
            score=0.99,
        ),
        CritiqueReport(candidate_index=1, defects=(), score=0.2),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[1]


def test_critique_ranking_falls_back_to_the_whole_pool_when_every_candidate_is_fatal() -> None:
    critiques = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.8,
        ),
        CritiqueReport(
            candidate_index=1,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.3,
        ),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[0]


def test_a_tied_score_is_broken_by_the_lowest_candidate_index() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.5),
        CritiqueReport(candidate_index=1, defects=(), score=0.5),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[0]


def test_selected_sql_is_always_the_qualified_statement_for_the_winning_index() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.1),
        CritiqueReport(candidate_index=1, defects=(), score=0.9),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected_sql == SQLS[1]
    assert selection.selected_sql != selection.selected.sql
