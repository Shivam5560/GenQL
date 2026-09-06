"""One real planning call against a real model. Costs money and needs network,
so it is gated on the key exactly as Phase 4's provider tests are — a clean
skip here is not a failure."""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.schema_link import SchemaLink
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.planning_service import PlanningService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

LINKS = (
    SchemaLink(
        object_qualified_name="local.tpcds.store_sales",
        column_names=("ss_store_sk", "ss_net_paid", "ss_sold_date_sk"),
        join_paths=("store_sales->store",),
    ),
    SchemaLink(
        object_qualified_name="local.tpcds.store",
        column_names=("s_store_sk", "s_store_name"),
    ),
)


def test_a_real_model_plans_against_the_links_it_was_given() -> None:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )

    plan = PlanningService(provider).plan("total net paid by store name", LINKS)

    assert plan.question == "total net paid by store name"
    assert plan.plan_text.strip()
    assert any("store_sales" in name for name in plan.referenced_objects)
