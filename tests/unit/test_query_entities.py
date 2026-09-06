"""Every Phase 5 entity is frozen: the graph passes them between nodes, and a
node mutating a neighbour's value in place would be invisible in a test."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.value_objects.guardrail_config import GuardrailConfig

PLAN = QueryPlan(
    question="how many stores are there",
    plan_text="count rows in tpcds.store",
    referenced_objects=("local.tpcds.store",),
)


def test_schema_link_defaults_every_collection_to_empty() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    assert link.column_names == ()
    assert link.join_paths == ()
    assert link.metric_names == ()
    assert link.domain_id is None


def test_schema_link_exposes_the_bare_object_name() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    assert link.schema_qualified_name == "tpcds.store"


def test_schema_link_is_frozen() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    with pytest.raises(ValidationError):
        link.object_qualified_name = "other"


def test_query_plan_coerces_referenced_objects_to_a_tuple() -> None:
    plan = QueryPlan(question="q", plan_text="p", referenced_objects=["a", "b"])

    assert plan.referenced_objects == ("a", "b")


def test_sql_candidate_carries_the_plan_it_was_generated_from() -> None:
    candidate = SqlCandidate(sql="SELECT 1", plan=PLAN)

    assert candidate.plan.question == "how many stores are there"


def test_guardrail_violation_defaults_to_unrepairable() -> None:
    violation = GuardrailViolation(rule_name="statement_kind", message="DELETE is not allowed")

    assert violation.repairable is False


def test_execution_result_is_frozen_and_keeps_row_order() -> None:
    result = ExecutionResult(columns=("n",), rows=((1,), (2,)), row_count=2, truncated=False)

    assert result.rows == ((1,), (2,))
    with pytest.raises(ValidationError):
        result.truncated = True


def test_guardrail_config_holds_an_immutable_allowlist() -> None:
    config = GuardrailConfig(
        row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset({"tpcds.store"})
    )

    assert "tpcds.store" in config.allowed_objects
    assert isinstance(config.allowed_objects, frozenset)
