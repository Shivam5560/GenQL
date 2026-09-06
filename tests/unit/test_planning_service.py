"""One ChatProvider call, one QueryPlan. The prompt assertions matter as much
as the happy path: a plan that is not grounded on the links it was given is
the exact failure mode the NL-planning stage exists to prevent."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, PlanningError
from genql.services.query.planning_service import PlanningService, build_planning_prompt

LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "total"),
        join_paths=("orders->customers",),
        metric_names=("net_revenue",),
    ),
    SchemaLink(object_qualified_name="local.shop.customers", column_names=("id", "email")),
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class RaisingChatProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        raise self._error


def test_the_plan_carries_the_question_the_caller_asked() -> None:
    chat = FakeChatProvider(
        {"plan_text": "join orders to customers", "referenced_objects": ["local.shop.orders"]}
    )

    plan = PlanningService(chat).plan("revenue by customer", LINKS)

    assert plan.question == "revenue by customer"
    assert plan.plan_text == "join orders to customers"
    assert plan.referenced_objects == ("local.shop.orders",)


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"plan_text": "p", "referenced_objects": []})

    PlanningService(chat).plan("q", LINKS)

    assert len(chat.prompts) == 1


def test_a_provider_failure_becomes_a_planning_error() -> None:
    service = PlanningService(RaisingChatProvider(ChatProviderError("502 from upstream")))

    with pytest.raises(PlanningError, match="502 from upstream"):
        service.plan("q", LINKS)


def test_an_unparseable_response_becomes_a_planning_error() -> None:
    chat = FakeChatProvider({"referenced_objects": []})  # plan_text missing

    with pytest.raises(PlanningError):
        PlanningService(chat).plan("q", LINKS)


def test_planning_without_links_is_refused_before_any_provider_call() -> None:
    chat = FakeChatProvider({"plan_text": "p", "referenced_objects": []})

    with pytest.raises(PlanningError, match="no schema links"):
        PlanningService(chat).plan("q", ())

    assert chat.prompts == []


def test_the_prompt_names_every_object_column_join_path_and_metric() -> None:
    prompt = build_planning_prompt("revenue by customer", LINKS)

    assert "local.shop.orders" in prompt
    assert "total" in prompt
    assert "orders->customers" in prompt
    assert "net_revenue" in prompt
    assert "revenue by customer" in prompt


def test_the_prompt_forbids_objects_outside_the_links() -> None:
    prompt = build_planning_prompt("revenue by customer", LINKS)

    assert "only the objects listed" in prompt.lower()


def test_a_validation_error_raised_by_the_provider_is_also_translated() -> None:
    class _Tiny(BaseModel):
        n: int

    try:
        _Tiny.model_validate({"n": "not a number"})
    except ValidationError as exc:
        service = PlanningService(RaisingChatProvider(exc))
        with pytest.raises(PlanningError):
            service.plan("q", LINKS)
