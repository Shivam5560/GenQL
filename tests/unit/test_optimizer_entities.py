"""Four new entities. The behaviour worth testing directly is the invariant
that ties OptimizationResult's two failure-facing fields together: a result
that is within budget must not carry a narrowing suggestion, and one that is
not must carry one. RewriteAndCostGateNode routes on `within_budget` and the
CLI prints `narrowing_suggestion`, so a result where those disagree would
either print an empty suggestion or silently execute an over-budget query."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.rewrite_outcome import RewriteOutcome

ACTUALS = ExecutionActuals(
    total_time_ms=12.5, rows=42, shared_buffers_hit=100, shared_buffers_read=7
)


def test_a_within_budget_result_carries_no_narrowing_suggestion() -> None:
    result = OptimizationResult(
        sql="SELECT 1",
        rules_applied=("predicate_pushdown",),
        estimated_cost=10.0,
        within_budget=True,
        narrowing_suggestion=None,
    )

    assert result.within_budget is True
    assert result.narrowing_suggestion is None


def test_a_within_budget_result_rejects_a_narrowing_suggestion() -> None:
    with pytest.raises(ValidationError):
        OptimizationResult(
            sql="SELECT 1",
            rules_applied=(),
            estimated_cost=10.0,
            within_budget=True,
            narrowing_suggestion="narrow the date range",
        )


def test_an_over_budget_result_requires_a_narrowing_suggestion() -> None:
    with pytest.raises(ValidationError):
        OptimizationResult(
            sql="SELECT 1",
            rules_applied=(),
            estimated_cost=1_000_000.0,
            within_budget=False,
            narrowing_suggestion=None,
        )


def test_an_over_budget_result_with_a_suggestion_is_valid() -> None:
    result = OptimizationResult(
        sql="SELECT 1",
        rules_applied=(),
        estimated_cost=1_000_000.0,
        within_budget=False,
        narrowing_suggestion="narrow the date range",
    )

    assert result.narrowing_suggestion == "narrow the date range"


def test_an_optimization_result_is_frozen() -> None:
    result = OptimizationResult(
        sql="SELECT 1", rules_applied=(), estimated_cost=1.0, within_budget=True
    )

    with pytest.raises(ValidationError):
        result.sql = "SELECT 2"


def test_execution_actuals_carry_the_four_explain_analyze_numbers() -> None:
    assert ACTUALS.total_time_ms == 12.5
    assert ACTUALS.rows == 42
    assert ACTUALS.shared_buffers_hit == 100
    assert ACTUALS.shared_buffers_read == 7


def test_a_rewrite_outcome_keys_on_the_sql_hash() -> None:
    outcome = RewriteOutcome(
        sql_hash="a" * 64,
        datasource_name="local",
        rules_applied=("projection_pruning",),
        estimated_cost=500.0,
        actuals=ACTUALS,
    )

    assert outcome.sql_hash == "a" * 64
    assert outcome.actuals.rows == 42


def test_an_index_recommendation_carries_its_supporting_evidence_count() -> None:
    recommendation = IndexRecommendation(
        object_qualified_name="local.tpcds.store_sales",
        column_name="ss_sold_date_sk",
        rationale="3 of 3 recorded executions filtered this column via sequential scan",
        supporting_execution_count=3,
    )

    assert recommendation.supporting_execution_count == 3
