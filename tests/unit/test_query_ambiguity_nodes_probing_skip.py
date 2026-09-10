"""AmbiguityProbingNode's critique-margin skip, split out of
test_query_ambiguity_nodes.py to stay under the house file-length limit: a
decisive critique score (a clear margin, or exactly one non-fatal survivor)
makes probing pure overhead, since CandidateSelectionService already falls
through to critique_ranked on an empty probe_results tuple."""

from __future__ import annotations

from genql.api.query_ambiguity_nodes import AmbiguityProbingNode
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from tests.unit.test_query_ambiguity_nodes import _contested_two_candidate_state


def test_ambiguity_probing_skips_when_critique_margin_clears_the_configured_bar() -> None:
    class FakeProbingService:
        def probe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = _contested_two_candidate_state()
    state["critique_reports"] = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.5),
    )

    update = AmbiguityProbingNode(FakeProbingService(), skip_margin=0.3)(state)

    assert update == {"probe_results": ()}


def test_ambiguity_probing_still_runs_when_the_margin_is_narrower_than_the_bar() -> None:
    probe = AmbiguityProbe(dimension="time_range", probe_sql="SELECT 1", candidate_predictions=())
    results = (ProbeResult(probe=probe, actual_result="x", resolved_candidate_index=0),)

    class FakeProbingService:
        def probe(self, plan, candidates, validated_sqls, critiques, datasource_name):  # type: ignore[no-untyped-def]
            return results

    state = _contested_two_candidate_state()
    state["critique_reports"] = (
        CritiqueReport(candidate_index=0, defects=(), score=0.6),
        CritiqueReport(candidate_index=1, defects=(), score=0.5),
    )

    update = AmbiguityProbingNode(FakeProbingService(), skip_margin=0.3)(state)

    assert update == {"probe_results": results}


def test_ambiguity_probing_never_skips_when_no_margin_is_configured() -> None:
    """The default: every caller from before this feature existed keeps
    running probing exactly as it always did."""
    probe = AmbiguityProbe(dimension="time_range", probe_sql="SELECT 1", candidate_predictions=())
    results = (ProbeResult(probe=probe, actual_result="x", resolved_candidate_index=0),)

    class FakeProbingService:
        def probe(self, plan, candidates, validated_sqls, critiques, datasource_name):  # type: ignore[no-untyped-def]
            return results

    state = _contested_two_candidate_state()
    state["critique_reports"] = (
        CritiqueReport(candidate_index=0, defects=(), score=0.99),
        CritiqueReport(candidate_index=1, defects=(), score=0.01),
    )

    update = AmbiguityProbingNode(FakeProbingService())(state)

    assert update == {"probe_results": results}


def test_ambiguity_probing_skip_ignores_fatal_candidates_when_ranking_the_margin() -> None:
    """A fatal candidate's low score must not count as "the runner-up" —
    selection would never pick it either way, so a wide margin against it
    proves nothing about whether the real contest was close."""

    class FakeProbingService:
        def probe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = _contested_two_candidate_state()
    state["critique_reports"] = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(
            candidate_index=1,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.0,
        ),
    )

    update = AmbiguityProbingNode(FakeProbingService(), skip_margin=0.3)(state)

    assert update == {"probe_results": ()}
