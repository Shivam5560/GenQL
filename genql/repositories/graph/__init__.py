"""Registers every graph-algorithm implementation with its registry.

This is the one place that imports the algorithm modules purely for their
`@CLUSTERING_ALGORITHMS.register(...)` / `@NODE_EMBEDDERS.register(...)`
decorator side effect.
"""

from __future__ import annotations

from genql.repositories.graph.clustering_algorithm_repository import (
    LeidenClusteringAlgorithm,
)
from genql.repositories.graph.fused_clustering_algorithm_repository import (
    FusedClusteringAlgorithm,
)
from genql.repositories.graph.join_path_miner_repository import WeightedShortestPathJoinPathMiner
from genql.repositories.graph.node_embedder_repository import FastRpNodeEmbedder

__all__ = [
    "LeidenClusteringAlgorithm",
    "FusedClusteringAlgorithm",
    "FastRpNodeEmbedder",
    "WeightedShortestPathJoinPathMiner",
]
