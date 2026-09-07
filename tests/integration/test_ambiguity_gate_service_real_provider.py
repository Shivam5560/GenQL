"""One real gate assessment against a live model, skipped cleanly without a key.

Two questions again, for the same reason as the intent test: a gate that always
said "ambiguous" would pass a one-sided test. The well-specified case is the
one that proves it discriminates, and it is also the case the parent spec's §20
cost model depends on — a gate that fires on everything makes the cheap path
disappear.
"""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.rule import Rule
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.ambiguity_gate_service import AmbiguityGateService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


class NoRules:
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        return ()


@pytest.fixture()
def gate() -> AmbiguityGateService:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return AmbiguityGateService(provider, NoRules(), 0.7)


def test_a_bare_two_word_question_is_judged_ambiguous(gate: AmbiguityGateService) -> None:
    assessment = gate.assess("show me revenue", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension is not None
    assert assessment.clarifying_question


def test_a_fully_specified_question_is_not_judged_ambiguous(
    gate: AmbiguityGateService,
) -> None:
    assessment = gate.assess(
        "for each store, total net paid on store sales in calendar year 2001, "
        "counting only completed sales, compared with calendar year 2000",
        "local",
    )

    assert assessment.is_ambiguous is False
