"""Estimated cost is a planner number, so the assertions are relative, never
absolute: a full scan of the largest fact table must estimate materially more
than the same query with a LIMIT. Asserting an absolute cost would encode this
machine's page counts into the suite."""

from __future__ import annotations

import pytest

from genql.domain.errors import CostEstimationError

pytestmark = pytest.mark.integration


def test_a_full_scan_estimates_more_than_the_same_query_limited(cost_estimator) -> None:
    full = cost_estimator.estimate("SELECT * FROM tpcds.store_sales", "local")
    limited = cost_estimator.estimate("SELECT * FROM tpcds.store_sales LIMIT 10", "local")

    assert full > limited


def test_estimating_never_executes_the_statement(cost_estimator) -> None:
    """A statement that would take minutes to run estimates instantly, which is
    only possible because EXPLAIN without ANALYZE does not run it."""
    cost = cost_estimator.estimate(
        "SELECT count(*) FROM tpcds.store_sales AS a, tpcds.store_sales AS b", "local"
    )

    assert cost > 0


def test_an_unparseable_statement_raises_a_typed_error(cost_estimator) -> None:
    with pytest.raises(CostEstimationError):
        cost_estimator.estimate("SELECT FROM WHERE", "local")


def test_reading_actuals_returns_measured_numbers(cost_estimator) -> None:
    actuals = cost_estimator.read_actuals("SELECT count(*) FROM tpcds.date_dim", "local")

    assert actuals.total_time_ms > 0
    assert actuals.rows >= 1
    assert actuals.shared_buffers_hit + actuals.shared_buffers_read > 0
