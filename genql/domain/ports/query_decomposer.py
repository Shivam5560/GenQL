"""One grounded LLM call that narrows an over-budget statement.

Given the plan, the statement, and the size of the gap, it returns a
simplified statement — a narrower date range, or a filter the static rules
could not prove safe on their own. It is the only model call in Phase 7, and
it is spent at most once per turn.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.query_plan import QueryPlan


@runtime_checkable
class QueryDecomposer(Protocol):
    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str: ...
