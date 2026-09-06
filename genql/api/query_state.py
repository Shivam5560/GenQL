"""The graph's shared state.

`violations` rather than a rendered message: the router needs the failure to
decide, the regeneration node needs it as feedback, and the CLI needs it in
the error it prints — a tuple of entities serves all three, a string serves
none of them well.

No checkpointer field and no thread id: Phase 5's graph is a single stateless
run from question to answer. Phase 6 adds PostgresSaver, per-thread advisory
locks, and interrupt() around this same state.
"""

from __future__ import annotations

from typing import TypedDict

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


class QueryState(TypedDict):
    question: str
    datasource_name: str
    domain_id: int | None
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    candidate: SqlCandidate | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]


def initial_state(question: str, datasource_name: str, domain_id: int | None = None) -> QueryState:
    return QueryState(
        question=question,
        datasource_name=datasource_name,
        domain_id=domain_id,
        links=None,
        plan=None,
        candidate=None,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
