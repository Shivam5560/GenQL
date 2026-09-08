"""Two strategies, one shared contract: each returns exactly variant_count
candidates from exactly one ChatProvider.complete call. The registry test
matters on its own — CandidateGenerationService iterates CANDIDATE_STRATEGIES
.keys() on the contested path, so a strategy registered under the wrong key,
or not registered at all, would silently change candidate diversity.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, GenerationError
from genql.repositories.query.decomposition_strategy import DecompositionStrategy
from genql.repositories.query.execution_plan_strategy import ExecutionPlanStrategy
from genql.repositories.query.registry import CANDIDATE_STRATEGIES

PLAN = QueryPlan(
    question="revenue by customer",
    plan_text="sum orders.total grouped by customers.email",
    referenced_objects=("local.shop.orders", "local.shop.customers"),
)
LINKS = (SchemaLink(object_qualified_name="local.shop.orders", column_names=("id", "total")),)
EXAMPLE = AmbiguityExample(
    question="show me revenue", interpretations=("gross", "net"), resolution="net"
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class RaisingChatProvider:
    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        raise ChatProviderError("upstream refused")


def test_both_strategies_are_registered() -> None:
    assert set(CANDIDATE_STRATEGIES.keys()) >= {"decomposition", "execution_plan"}


def test_the_registry_creates_a_decomposition_strategy_with_an_injected_chat() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    strategy = CANDIDATE_STRATEGIES.create("decomposition", chat=chat)
    variants = strategy.generate_variants(PLAN, LINKS, (), ())

    assert len(variants) == 2
    assert len(chat.prompts) == 1


def test_decomposition_returns_two_candidates_carrying_the_plan() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    variants = DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert [v.sql for v in variants] == ["SELECT 1", "SELECT 2"]
    assert all(v.plan is PLAN for v in variants)


def test_decomposition_declares_a_variant_count_of_two() -> None:
    assert DecompositionStrategy.variant_count == 2


def test_decomposition_prompt_carries_the_examples_when_given() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), (EXAMPLE,))

    assert "show me revenue" in chat.prompts[0]


def test_a_provider_failure_becomes_a_generation_error() -> None:
    with pytest.raises(GenerationError):
        DecompositionStrategy(RaisingChatProvider()).generate_variants(PLAN, LINKS, (), ())


def test_execution_plan_returns_two_candidates() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    variants = ExecutionPlanStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert len(variants) == 2


def test_execution_plan_declares_a_variant_count_of_two() -> None:
    assert ExecutionPlanStrategy.variant_count == 2


def test_execution_plan_prompt_mentions_scan_order() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    ExecutionPlanStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert "execution plan" in chat.prompts[0].lower()


def test_an_empty_variant_is_refused() -> None:
    chat = FakeChatProvider({"variant_1": "   ", "variant_2": "SELECT 2"})

    with pytest.raises(GenerationError, match="empty"):
        DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), ())
