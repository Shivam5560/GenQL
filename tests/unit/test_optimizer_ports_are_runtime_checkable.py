"""Every port is a runtime_checkable Protocol, matching every port since
Phase 1. The check is cheap and catches the one mistake that is otherwise
invisible until composition: a Protocol declared without the decorator, which
makes `isinstance` raise rather than answer."""

from __future__ import annotations

from collections.abc import Sequence

import sqlglot
from sqlglot import exp

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.ports.cost_estimator import CostEstimator
from genql.domain.ports.execution_actuals_reader import ExecutionActualsReader
from genql.domain.ports.index_recommender import IndexRecommender
from genql.domain.ports.query_decomposer import QueryDecomposer
from genql.domain.ports.rewrite_outcome_writer import RewriteOutcomeWriter
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory


class _Rule:
    name = "noop"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression


class _Factory:
    def rules(self) -> Sequence[RewriteRule]:
        return (_Rule(),)


class _Estimator:
    def estimate(self, sql: str, datasource_name: str) -> float:
        return 1.0


class _ActualsReader:
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        return ExecutionActuals(
            total_time_ms=1.0, rows=1, shared_buffers_hit=1, shared_buffers_read=0
        )


class _Decomposer:
    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str:
        return sql


class _Writer:
    def write(self, outcome: RewriteOutcome) -> None:
        return None


class _Recommender:
    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return ()


def test_every_optimizer_port_is_runtime_checkable() -> None:
    assert isinstance(_Rule(), RewriteRule)
    assert isinstance(_Factory(), RewriteRuleFactory)
    assert isinstance(_Estimator(), CostEstimator)
    assert isinstance(_ActualsReader(), ExecutionActualsReader)
    assert isinstance(_Decomposer(), QueryDecomposer)
    assert isinstance(_Writer(), RewriteOutcomeWriter)
    assert isinstance(_Recommender(), IndexRecommender)


def test_a_rewrite_rule_returns_an_expression_not_none() -> None:
    """The contract OptimizationService's identity comparison depends on."""
    expression = sqlglot.parse_one("SELECT 1", dialect="postgres")

    assert _Rule().apply(expression) is expression
