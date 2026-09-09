"""Each node opens with the same guard: not contested, or one surviving
candidate, short-circuits to the empty (or single-survivor) case with no
service call at all — the whole demand-driven claim, tested directly here
rather than only at the graph level."""

from __future__ import annotations

import pytest

from genql.api.query_ambiguity_nodes import (
    AmbiguityProbingNode,
    CandidateSelectionNode,
    CritiqueNode,
)
from genql.api.query_state import initial_state
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import CritiqueError

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())
CANDIDATE_A = SqlCandidate(sql="A", plan=PLAN)
CANDIDATE_B = SqlCandidate(sql="B", plan=PLAN)
NON_FATAL = (CritiqueReport(candidate_index=0, defects=(), score=0.9),)
ALL_FATAL = (
    CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="fatal", message="m"),),
        score=0.1,
    ),
    CritiqueReport(
        candidate_index=1,
        defects=(Defect(dimension=None, severity="fatal", message="m"),),
        score=0.2,
    ),
)


class FakeCritic:
    def __init__(self, reports: tuple[CritiqueReport, ...]) -> None:
        self._reports = reports
        self.calls = 0

    def critique(self, plan, candidates, validated_sqls, links) -> tuple[CritiqueReport, ...]:
        self.calls += 1
        return self._reports


def _contested_two_candidate_state():  # type: ignore[no-untyped-def]
    state = initial_state("q", "local", "t-1")
    state["contested"] = True
    state["plan"] = PLAN
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)
    state["validated_sqls"] = ("SELECT A", "SELECT B")
    return state


def test_critique_skips_entirely_when_not_contested() -> None:
    critic = FakeCritic(NON_FATAL)
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)

    update = CritiqueNode(critic)(state)

    assert update == {"critique_reports": ()}
    assert critic.calls == 0


def test_critique_skips_with_a_single_survivor_even_when_contested() -> None:
    critic = FakeCritic(NON_FATAL)
    state = initial_state("q", "local", "t-1")
    state["contested"] = True
    state["candidates"] = (CANDIDATE_A,)

    update = CritiqueNode(critic)(state)

    assert update == {"critique_reports": ()}
    assert critic.calls == 0


def test_critique_writes_the_reports_when_not_all_fatal() -> None:
    critic = FakeCritic(NON_FATAL)

    update = CritiqueNode(critic)(_contested_two_candidate_state())

    assert update == {"critique_reports": NON_FATAL}


def test_critique_grants_the_escalated_retry_the_first_time_all_are_fatal() -> None:
    critic = FakeCritic(ALL_FATAL)
    state = _contested_two_candidate_state()

    update = CritiqueNode(critic)(state)

    assert update["escalated"] is True
    assert update["critique_reports"] == ALL_FATAL


def test_critique_raises_once_the_escalation_budget_is_already_spent() -> None:
    critic = FakeCritic(ALL_FATAL)
    state = _contested_two_candidate_state()
    state["escalated"] = True

    with pytest.raises(CritiqueError):
        CritiqueNode(critic)(state)


def test_ambiguity_probing_skips_entirely_when_not_contested() -> None:
    class FakeProbingService:
        def probe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)

    update = AmbiguityProbingNode(FakeProbingService())(state)

    assert update == {"probe_results": ()}


def test_ambiguity_probing_calls_the_service_when_contested_with_multiple_candidates() -> None:
    probe = AmbiguityProbe(dimension="time_range", probe_sql="SELECT 1", candidate_predictions=())
    results = (ProbeResult(probe=probe, actual_result="x", resolved_candidate_index=0),)

    class FakeProbingService:
        def probe(self, plan, candidates, validated_sqls, critiques, datasource_name):  # type: ignore[no-untyped-def]
            return results

    update = AmbiguityProbingNode(FakeProbingService())(_contested_two_candidate_state())

    assert update == {"probe_results": results}


def test_candidate_selection_short_circuits_a_single_survivor() -> None:
    class FakeSelectionService:
        def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A,)
    state["validated_sqls"] = ("SELECT A",)

    update = CandidateSelectionNode(FakeSelectionService())(state)

    assert update["selection"].method == "single_survivor"
    assert update["selection"].selected is CANDIDATE_A
    assert update["validated_sql"] == "SELECT A"


def test_candidate_selection_short_circuits_when_not_contested_even_with_two_candidates() -> None:
    """Defence in depth: this shape should not occur (the non-contested path
    only ever produces one candidate), but the guard still protects it."""

    class FakeSelectionService:
        def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)
    state["validated_sqls"] = ("SELECT A", "SELECT B")

    update = CandidateSelectionNode(FakeSelectionService())(state)

    assert update["selection"].method == "single_survivor"
    assert update["selection"].selected is CANDIDATE_A


def test_candidate_selection_calls_the_service_when_contested_with_multiple_candidates() -> None:
    selection = CandidateSelection(
        selected=CANDIDATE_B, selected_sql="SELECT B", method="critique_ranked", rationale="r"
    )

    class FakeSelectionService:
        def select(self, candidates, validated_sqls, critiques, probe_results):  # type: ignore[no-untyped-def]
            return selection

    update = CandidateSelectionNode(FakeSelectionService())(_contested_two_candidate_state())

    assert update == {"selection": selection, "validated_sql": "SELECT B"}
