"""The graph's shared state.

`violations` rather than a rendered message: the router needs the failure to
decide, the regeneration node needs it as feedback, and the CLI needs it in
the error it prints — a tuple of entities serves all three, a string serves
none of them well.

`clarifications` is what makes the interrupt loop terminate. Each pause
appends one (dimension, answer) pair, and the gate treats an answered
dimension as resolved, so the set of dimensions it can still ask about
strictly shrinks toward empty. It is also, literally, the parent spec's §13
"structured state, not appended chat text": what persists is which dimension
was settled and how, not a transcript.

`thread_id` is required rather than optional: every turn has one, including a
turn that finishes without pausing, because a follow-up question needs
something to attach to.
"""

from __future__ import annotations

from typing import TypedDict

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


class QueryState(TypedDict):
    question: str
    datasource_name: str
    thread_id: str
    domain_id: int | None
    intent: str | None
    ambiguity: AmbiguityAssessment | None
    clarifications: tuple[tuple[str, str], ...]
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    candidate: SqlCandidate | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]


def initial_state(
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> QueryState:
    return QueryState(
        question=question,
        datasource_name=datasource_name,
        thread_id=thread_id,
        domain_id=domain_id,
        intent=None,
        ambiguity=None,
        clarifications=(),
        links=None,
        plan=None,
        candidate=None,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
