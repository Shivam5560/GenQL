"""The claim Phase 7 exists to make: an unaffordable query is explained, not
executed — and the same query under a realistic budget runs normally.

Two runs of one question, differing only in `cost_budget`, so the assertion is
about the gate rather than about the question.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest
from dependency_injector import providers

from genql.api.query_turn import start_turn
from genql.composition_root import Container
from genql.core.settings import Settings
from genql.domain.entities.turn_response import TurnResponse

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_provider,
    # `real_provider` is a label, not a gate: the skip has to be explicit, the
    # same way every other real-provider module in this suite does it.
    pytest.mark.skipif(
        not os.environ.get("GENQL_OPENROUTER_API_KEY"),
        reason="requires GENQL_OPENROUTER_API_KEY",
    ),
    pytest.mark.skipif_no_tpcds,
]

EXPENSIVE = "join every store sale to every catalog sale and count the pairs"


@pytest.fixture()
def turn_with_budget() -> Callable[..., TurnResponse]:
    """One real turn through the fully-wired Container, with only
    `cost_budget` changed.

    The override is ad hoc: it rebuilds the whole `settings` provider because
    that is the only seam a declarative container offers today. Part B's Task 17
    introduces `Container.with_overrides`; come back here then and collapse this
    into it.
    """

    def _turn(question: str, cost_budget: float) -> TurnResponse:
        container = Container()
        container.settings.override(providers.Singleton(Settings, cost_budget=cost_budget))
        return start_turn(
            container.query_graph(), container.thread_lock_factory(), question, "local"
        )

    return _turn


def test_an_over_budget_question_returns_a_suggestion_and_no_rows(
    turn_with_budget: Callable[..., TurnResponse],
) -> None:
    response = turn_with_budget(EXPENSIVE, cost_budget=1.0)

    assert response.result is None
    assert response.narrowing_suggestion is not None
    assert response.validated_sql is not None  # the user sees what was declined


def test_the_same_question_under_a_realistic_budget_executes(
    turn_with_budget: Callable[..., TurnResponse],
) -> None:
    response = turn_with_budget("how many rows are in the date dimension", cost_budget=1e9)

    assert response.result is not None
    assert response.narrowing_suggestion is None
