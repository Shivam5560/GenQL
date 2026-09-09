"""Three behaviours: the prompt carries the numbers the model needs to narrow
by the right amount, the returned SQL is unwrapped from any markdown fence,
and a provider that returns nothing usable yields the original statement
rather than an empty one — an empty statement would fail cost estimation and
turn a recoverable over-budget turn into a crash.

`_Chat.complete` mirrors `ChatProvider`'s real signature
(`complete(self, prompt, response_schema) -> T`) rather than the
`complete(self, prompt) -> str` shape a naive adapter might assume: it builds
and returns an instance of whatever `response_schema` is passed.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.query_plan import QueryPlan
from genql.services.query.query_decomposer import LlmQueryDecomposer

T = TypeVar("T", bound=BaseModel)

PLAN = QueryPlan(
    question="total sales by month",
    plan_text="sum ss_ext_sales_price grouped by month",
    referenced_objects=("local.tpcds.store_sales",),
)
SQL = "SELECT sum(ss_ext_sales_price) FROM tpcds.store_sales"


class _Chat:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.prompts.append(prompt)
        return response_schema(sql=self.reply)


def test_the_prompt_carries_the_statement_the_cost_and_the_budget() -> None:
    chat = _Chat("SELECT 1")
    LlmQueryDecomposer(chat).decompose(PLAN, SQL, 500_000.0, 100_000.0)

    prompt = chat.prompts[0]
    assert SQL in prompt
    assert "500000" in prompt.replace(",", "").replace(".0", "")
    assert "100000" in prompt.replace(",", "").replace(".0", "")
    assert PLAN.plan_text in prompt


def test_a_fenced_reply_is_unwrapped_to_bare_sql() -> None:
    chat = _Chat("```sql\nSELECT 1 LIMIT 10\n```")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == "SELECT 1 LIMIT 10"


def test_an_empty_reply_yields_the_original_statement() -> None:
    chat = _Chat("   ")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == SQL


def test_a_reply_that_is_not_a_select_yields_the_original_statement() -> None:
    """The decomposed statement goes straight to cost estimation and then to
    guarded execution. A DELETE here would be caught by the guardrails, but
    refusing it at the source keeps the failure legible."""
    chat = _Chat("DELETE FROM tpcds.store_sales")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == SQL
