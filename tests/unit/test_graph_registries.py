"""The three graph registries exist and are independent of each other."""

from __future__ import annotations

from genql.repositories.graph.registry import (
    CLUSTERING_ALGORITHMS,
    JOIN_PATH_STRATEGIES,
    NODE_EMBEDDERS,
)


def test_the_three_registries_are_distinct() -> None:
    assert CLUSTERING_ALGORITHMS.name == "clustering_algorithms"
    assert NODE_EMBEDDERS.name == "node_embedders"
    assert JOIN_PATH_STRATEGIES.name == "join_path_strategies"
