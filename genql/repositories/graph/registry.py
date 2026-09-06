"""The three graph-algorithm registries, keyed by algorithm name.

Adding an algorithm — `louvain` alongside `leiden`, say — is one file plus
one decorator. `Settings` picks the active key; no call site names a class.
"""

from __future__ import annotations

from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.node_embedder import NodeEmbedder
from genql.registries.registry import Registry

CLUSTERING_ALGORITHMS: Registry[ClusteringAlgorithm] = Registry("clustering_algorithms")
NODE_EMBEDDERS: Registry[NodeEmbedder] = Registry("node_embedders")
JOIN_PATH_STRATEGIES: Registry[JoinPathMiner] = Registry("join_path_strategies")
