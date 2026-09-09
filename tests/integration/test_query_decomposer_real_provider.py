"""One real narrowing call against a live model, skipped cleanly without a
key. Asserts only that the reply parses as a SELECT and differs from the
input — never specific SQL text from a live model."""

from __future__ import annotations

import os

import pytest
import sqlglot
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.ports.chat_provider import ChatProvider
from genql.services.query.query_decomposer import LlmQueryDecomposer

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

PLAN = QueryPlan(
    question="total sales by month",
    plan_text="sum ss_ext_sales_price grouped by month, over the full history",
    referenced_objects=("local.tpcds.store_sales",),
)
SQL = "SELECT sum(ss_ext_sales_price) FROM tpcds.store_sales"


def test_a_real_model_narrows_an_over_budget_statement(
    openrouter_chat_provider: ChatProvider,
) -> None:
    narrowed = LlmQueryDecomposer(openrouter_chat_provider).decompose(
        PLAN, SQL, 500_000.0, 100_000.0
    )

    parsed = sqlglot.parse_one(narrowed, dialect="postgres")
    assert isinstance(parsed, exp.Select | exp.Subquery) or parsed.find(exp.Select)
    assert narrowed != SQL
