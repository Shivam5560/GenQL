"""The golden run's three fixtures, all resolved from a real Container.

Nothing is stubbed. The point of this directory is to measure the pipeline as
it actually ships, so a fake anywhere in it would make the number it produces
a statement about the fake.

`golden_turn_runner` is a factory rather than a runner because each test runs
the whole set, and it goes through TurnRunnerFactory with the `full` ablation
rather than reaching for `container.turn_runner()` so that this run is on
exactly the pipeline AblationService calls its baseline — otherwise the
accuracy recorded here and the `full` row of an ablation table would be two
different measurements sharing one name.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from genql.composition_root import Container
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.ports.turn_runner import TurnRunner
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.registry import ABLATIONS

DATASOURCE = "local"


@pytest.fixture(scope="session")
def container() -> Container:
    return Container()


@pytest.fixture()
def golden_runner(container: Container) -> GoldenEvaluationService:
    service: GoldenEvaluationService = container.golden_evaluation_service()
    return service


@pytest.fixture()
def golden_cases(container: Container) -> tuple[GoldenCase, ...]:
    cases: tuple[GoldenCase, ...] = container.golden_set_reader().read_cases(DATASOURCE)
    return cases


@pytest.fixture()
def golden_turn_runner(container: Container) -> Callable[[], TurnRunner]:
    def _build() -> TurnRunner:
        runner: TurnRunner = container.turn_runner_factory().for_ablation(ABLATIONS.create("full"))
        return runner

    return _build
