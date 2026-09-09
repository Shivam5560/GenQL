"""Every branch of the gate, against fakes. The three that matter most:
within-budget after static rewriting never calls the decomposer (it is the
only LLM call in the phase and it must stay demand-driven), an over-budget
query that decomposition rescues reports the decomposed statement, and one
decomposition cannot rescue returns a suggestion rather than raising."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import CostEstimationError
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.services.query.optimization_service import OptimizationService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "cid", "total"),
    ),
)
SQL = "SELECT id FROM shop.orders WHERE total > 10"


class _LimitRule:
    """Changes the statement, so OptimizationService must record it as fired."""

    name = "adds_a_limit"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression.limit(100)


class _NoopRule:
    name = "does_nothing"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression


class _Factory:
    def __init__(self, *rules: RewriteRule) -> None:
        self._rules = rules

    def rules(self) -> Sequence[RewriteRule]:
        return self._rules


class _Estimator:
    def __init__(self, *costs: float) -> None:
        self._costs = list(costs)
        self.calls: list[str] = []

    def estimate(self, sql: str, datasource_name: str) -> float:
        self.calls.append(sql)
        return self._costs.pop(0) if self._costs else 1.0


class _RaisingEstimator:
    def __init__(self, first: float) -> None:
        self._first = first
        self.calls = 0

    def estimate(self, sql: str, datasource_name: str) -> float:
        self.calls += 1
        if self.calls == 1:
            return self._first
        raise CostEstimationError("boom")


class _Decomposer:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str:
        self.calls += 1
        return self.reply


def _service(factory, estimator, decomposer, budget=100.0) -> OptimizationService:
    return OptimizationService(
        rules=factory, estimator=estimator, decomposer=decomposer, budget=budget
    )


def test_a_rule_that_changes_the_statement_is_recorded_as_applied() -> None:
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.rules_applied == ("adds_a_limit",)
    assert "LIMIT 100" in result.sql


def test_a_rule_that_changes_nothing_is_not_recorded() -> None:
    service = _service(_Factory(_NoopRule()), _Estimator(10.0), _Decomposer(SQL))

    assert service.optimize(PLAN, SQL, LINKS, "local").rules_applied == ()


def test_a_within_budget_statement_never_calls_the_decomposer() -> None:
    decomposer = _Decomposer(SQL)
    service = _service(_Factory(_NoopRule()), _Estimator(10.0), decomposer)

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is True
    assert result.narrowing_suggestion is None
    assert decomposer.calls == 0


def test_an_over_budget_statement_decomposition_rescues_is_within_budget() -> None:
    decomposer = _Decomposer("SELECT id FROM shop.orders WHERE total > 1000")
    # First estimate: over budget. Second (the decomposed statement): under.
    service = _service(_Factory(_NoopRule()), _Estimator(5_000.0, 50.0), decomposer)

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is True
    assert result.estimated_cost == 50.0
    assert result.sql == "SELECT id FROM shop.orders WHERE total > 1000"
    assert decomposer.calls == 1


def test_decomposition_is_attempted_exactly_once() -> None:
    decomposer = _Decomposer(SQL)
    service = _service(_Factory(_NoopRule()), _Estimator(5_000.0, 4_000.0), decomposer)

    service.optimize(PLAN, SQL, LINKS, "local")

    assert decomposer.calls == 1


def test_a_statement_still_over_budget_returns_a_suggestion_and_never_raises() -> None:
    service = _service(
        _Factory(_NoopRule()), _Estimator(5_000.0, 4_000.0), _Decomposer(SQL), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is False
    assert result.narrowing_suggestion is not None
    assert "40" in result.narrowing_suggestion  # 4000 / 100 = 40x the budget


def test_a_decomposition_that_costs_more_is_discarded() -> None:
    service = _service(
        _Factory(_NoopRule()), _Estimator(5_000.0, 9_000.0), _Decomposer("SELECT 1"), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.estimated_cost == 5_000.0
    assert result.sql != "SELECT 1"


def test_a_failed_estimate_of_the_decomposed_statement_keeps_the_rewritten_one() -> None:
    service = _service(
        _Factory(_NoopRule()), _RaisingEstimator(5_000.0), _Decomposer("SELECT 1"), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.estimated_cost == 5_000.0
    assert result.within_budget is False


def test_a_statement_that_cannot_be_qualified_is_cost_gated_without_rewriting() -> None:
    """A column no link declares makes qualification raise. The statement is
    already valid — static validation passed it — so it must still be gated,
    just not rewritten."""
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(PLAN, "SELECT unknown_column FROM shop.orders", LINKS, "local")

    assert result.rules_applied == ()
    assert result.sql == "SELECT unknown_column FROM shop.orders"
    assert result.within_budget is True


def test_an_unparseable_statement_is_cost_gated_without_rewriting() -> None:
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(PLAN, "SELECT FROM WHERE", LINKS, "local")

    assert result.rules_applied == ()
    assert result.sql == "SELECT FROM WHERE"


def test_a_cost_estimation_failure_on_the_first_estimate_propagates() -> None:
    """Unlike the decomposed statement's estimate, this one has no fallback:
    a gate that cannot estimate at all has not gated anything, and silently
    executing would defeat the stage."""

    class _AlwaysRaises:
        def estimate(self, sql: str, datasource_name: str) -> float:
            raise CostEstimationError("boom")

    service = _service(_Factory(_NoopRule()), _AlwaysRaises(), _Decomposer(SQL))

    with pytest.raises(CostEstimationError):
        service.optimize(PLAN, SQL, LINKS, "local")
