"""One real generation call. Asserts the statement parses as a SELECT rather
than asserting its exact text — the point is that a real model, given a real
plan and real links, produces something static validation can even look at."""

from __future__ import annotations

import os

import pytest
import sqlglot
from sqlglot import exp

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.candidate_generation_service import CandidateGenerationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

PLAN = QueryPlan(
    question="total net paid by store name",
    plan_text=(
        "Join store_sales to store on ss_store_sk = s_store_sk, sum ss_net_paid, "
        "group by s_store_name."
    ),
    referenced_objects=("local.tpcds.store_sales", "local.tpcds.store"),
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.tpcds.store_sales",
        column_names=("ss_store_sk", "ss_net_paid"),
        join_paths=("store_sales->store",),
    ),
    SchemaLink(
        object_qualified_name="local.tpcds.store",
        column_names=("s_store_sk", "s_store_name"),
    ),
)


class _UnusedExampleReader:
    """Non-contested generation never fetches examples; a real reader isn't
    needed for this test and would require its own live infrastructure."""

    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        raise AssertionError("non-contested generation must not fetch examples")


def test_a_real_model_produces_a_parseable_select() -> None:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    service = CandidateGenerationService(
        chat=provider,
        escalation_chat=provider,
        examples=_UnusedExampleReader(),
        example_top_k=3,
    )

    candidates = service.generate(PLAN, LINKS, contested=False)

    assert len(candidates) == 1
    expression = sqlglot.parse_one(candidates[0].sql, dialect="postgres")
    assert isinstance(expression, exp.Select | exp.Union)
    assert "store_sales" in candidates[0].sql.lower()
