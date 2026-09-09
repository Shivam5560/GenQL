"""Two properties carry the harness. Every ablation must get its own runner —
sharing one would measure the baseline five times and report five identical
"no delta" results. And a recompiling ablation must restore the store even
when its run raises, because a left-behind ablated compile silently degrades
every subsequent turn, including real user turns."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import UnknownAblationError
from genql.services.eval.ablation_service import AblationService

CASE = GoldenCase(
    case_id="c1",
    question="q",
    datasource_name="local",
    reference_sql="SELECT 1",
    failure_class="ambiguous_intent",
)


class _Runner:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        raise AssertionError("the evaluation fake should be driving this")


class _Runners:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def for_ablation(self, ablation: Ablation) -> _Runner:
        self.requested.append(ablation.name)
        return _Runner(ablation.name)


class _Recompiler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def recompile(self, ablation: Ablation, datasource_name: str) -> int:
        self.calls.append(ablation.name)
        return 24


class _Evaluation:
    def __init__(self) -> None:
        self.ablations: list[str] = []

    def run(self, ablation_name: str, cases: Sequence[GoldenCase], runner) -> GoldenRunReport:  # type: ignore[no-untyped-def]
        self.ablations.append(ablation_name)
        return GoldenRunReport(ablation_name=ablation_name, outcomes=())


class _RaisingEvaluation(_Evaluation):
    def run(self, ablation_name, cases, runner):  # type: ignore[no-untyped-def]
        raise RuntimeError("the run exploded")


def _service(evaluation, runners, recompiler) -> AblationService:
    return AblationService(evaluation=evaluation, runners=runners, recompiler=recompiler)


def test_each_named_ablation_produces_one_report() -> None:
    evaluation = _Evaluation()

    reports = _service(evaluation, _Runners(), _Recompiler()).run(("full", "no_domains"), (CASE,))

    assert [r.ablation_name for r in reports] == ["full", "no_domains"]


def test_each_ablation_gets_its_own_runner() -> None:
    runners = _Runners()

    _service(_Evaluation(), runners, _Recompiler()).run(("full", "no_domains"), (CASE,))

    assert runners.requested == ["full", "no_domains"]


def test_an_unknown_ablation_raises_and_names_the_registered_ones() -> None:
    with pytest.raises(UnknownAblationError) as exc:
        _service(_Evaluation(), _Runners(), _Recompiler()).run(("invented",), (CASE,))

    assert "no_domains" in str(exc.value)


def test_a_non_recompiling_ablation_never_touches_the_search_documents() -> None:
    recompiler = _Recompiler()

    _service(_Evaluation(), _Runners(), recompiler).run(("full", "no_domains"), (CASE,))

    assert recompiler.calls == []


def test_a_recompiling_ablation_compiles_before_and_restores_after() -> None:
    recompiler = _Recompiler()

    _service(_Evaluation(), _Runners(), recompiler).run(("no_descriptions",), (CASE,))

    assert recompiler.calls == ["no_descriptions", "full"]


def test_the_store_is_restored_even_when_the_run_raises() -> None:
    recompiler = _Recompiler()

    with pytest.raises(RuntimeError):
        _service(_RaisingEvaluation(), _Runners(), recompiler).run(("no_descriptions",), (CASE,))

    assert recompiler.calls == ["no_descriptions", "full"]


def test_running_no_names_runs_every_registered_ablation() -> None:
    evaluation = _Evaluation()

    _service(evaluation, _Runners(), _Recompiler()).run((), (CASE,))

    assert "full" in evaluation.ablations
    assert len(evaluation.ablations) == 6


def test_an_empty_case_set_still_produces_one_report_per_ablation() -> None:
    reports = _service(_Evaluation(), _Runners(), _Recompiler()).run(("full",), ())

    assert len(reports) == 1
    assert reports[0].outcomes == ()
