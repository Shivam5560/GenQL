"""The one LLM call Phase 7 makes, spent at most once per turn.

It is asked to narrow, never to rewrite for speed: the static rules already
did every transform that is provably safe, so what is left is a semantic
decision — a shorter date range, a filter the plan implies but the SQL did not
state — that only a model reading the plan can make.

Every unusable reply falls back to the original statement rather than raising.
The caller has already decided this query is over budget; a failed narrowing
attempt means it stays over budget and the user gets a suggestion, which is a
worse outcome than a narrowed query but a much better one than a crashed turn.

Per Deviation 7, a ChatProviderError from the model call is not wrapped here;
it propagates as-is.
"""

from __future__ import annotations

import sqlglot
from pydantic import BaseModel, ConfigDict
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.ports.chat_provider import ChatProvider

_PROMPT = """You are narrowing a SQL statement that is too expensive to run.

The user asked: {question}

The plan the statement implements:
{plan_text}

The statement:
{sql}

Its estimated planner cost is {estimated_cost:.0f}, and the budget is {budget:.0f}.

Return ONE SELECT statement that answers the same question over a smaller slice
of data — a narrower date range, a more selective filter the plan implies, or a
smaller grain. Do not change which columns are returned. Do not add a LIMIT.
Reply with the SQL only, no explanation and no markdown fence."""


class DecompositionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str


def _unfence(reply: str) -> str:
    text = reply.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _is_select(sql: str) -> bool:
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError:
        return False
    return isinstance(parsed, exp.Select | exp.Subquery) or bool(parsed.find(exp.Select))


class LlmQueryDecomposer:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str:
        response = self._chat.complete(
            _PROMPT.format(
                question=plan.question,
                plan_text=plan.plan_text,
                sql=sql,
                estimated_cost=estimated_cost,
                budget=budget,
            ),
            DecompositionResponse,
        )
        candidate = _unfence(response.sql)
        if not candidate or not _is_select(candidate):
            return sql
        return candidate
