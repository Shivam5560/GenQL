"""One ChatProvider call, one SqlCandidate. The retry-feedback assertions are
the load-bearing ones: without the previous attempt's violations in the
prompt, the graph's retry edge would hand the generator identical inputs and
get identical SQL back."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, GenerationError
from genql.services.query.candidate_generation_service import (
    CandidateGenerationService,
    build_generation_prompt,
)

PLAN = QueryPlan(
    question="revenue by customer",
    plan_text="sum orders.total grouped by customers.email",
    referenced_objects=("local.shop.orders", "local.shop.customers"),
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "total", "customer_id"),
        join_paths=("orders->customers",),
        metric_names=("net_revenue",),
    ),
    SchemaLink(object_qualified_name="local.shop.customers", column_names=("id", "email")),
)
VIOLATIONS = (
    GuardrailViolation(
        rule_name="object_allowlist",
        message="object(s) not in the semantic store for this datasource: shop.invoices",
    ),
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


def test_the_candidate_carries_the_plan_it_came_from() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    candidate = CandidateGenerationService(chat).generate(PLAN, LINKS)

    assert candidate.sql == "SELECT 1"
    assert candidate.plan is PLAN


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    CandidateGenerationService(chat).generate(PLAN, LINKS)

    assert len(chat.prompts) == 1


def test_a_provider_failure_becomes_a_generation_error() -> None:
    with pytest.raises(GenerationError, match="upstream refused"):
        CandidateGenerationService(RaisingChatProvider()).generate(PLAN, LINKS)


def test_an_unparseable_response_becomes_a_generation_error() -> None:
    chat = FakeChatProvider({})  # sql missing

    with pytest.raises(GenerationError):
        CandidateGenerationService(chat).generate(PLAN, LINKS)


def test_an_empty_sql_string_is_refused() -> None:
    chat = FakeChatProvider({"sql": "   "})

    with pytest.raises(GenerationError, match="empty"):
        CandidateGenerationService(chat).generate(PLAN, LINKS)


def test_generating_without_links_is_refused_before_any_provider_call() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    with pytest.raises(GenerationError, match="no schema links"):
        CandidateGenerationService(chat).generate(PLAN, ())

    assert chat.prompts == []


def test_the_first_attempt_prompt_carries_the_plan_and_the_links() -> None:
    prompt = build_generation_prompt(PLAN, LINKS, ())

    assert "sum orders.total grouped by customers.email" in prompt
    assert "local.shop.orders" in prompt
    assert "customer_id" in prompt
    assert "previous attempt" not in prompt.lower()


def test_the_retry_prompt_carries_the_previous_violations() -> None:
    prompt = build_generation_prompt(PLAN, LINKS, VIOLATIONS)

    assert "previous attempt" in prompt.lower()
    assert "object_allowlist" in prompt
    assert "shop.invoices" in prompt


def test_the_violations_reach_the_provider_prompt() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    CandidateGenerationService(chat).generate(PLAN, LINKS, VIOLATIONS)

    assert "object_allowlist" in chat.prompts[0]
