"""Phase 7's eight providers resolve, and the recording switch is the only
thing that changes shape between the two configurations."""

from __future__ import annotations

import pytest

from genql.composition_root import Container


def test_the_container_builds_the_optimizer_repositories(container: Container) -> None:
    assert hasattr(container.cost_estimator(), "estimate")
    assert hasattr(container.rewrite_outcome_writer(), "write")
    assert hasattr(container.index_recommender(), "recommend")


def test_the_container_builds_an_optimization_service(container: Container) -> None:
    assert hasattr(container.rewrite_rule_factory(), "rules")
    assert hasattr(container.query_decomposer(), "decompose")
    assert hasattr(container.optimization_service(), "optimize")


def test_the_container_builds_an_index_recommendation_service(container: Container) -> None:
    assert hasattr(container.index_recommendation_service(), "recommend")


def test_the_recording_service_is_none_unless_actuals_recording_is_enabled(
    container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disabled-by-default switch is read in exactly one place: this
    provider returns None, and GuardedExecutionNode's `is not None` does the
    rest. Nothing else in the graph changes shape between the two settings."""
    assert container.rewrite_recording_service() is None

    monkeypatch.setenv("GENQL_RECORD_EXECUTION_ACTUALS", "true")
    enabled = Container()
    assert hasattr(enabled.rewrite_recording_service(), "record")
