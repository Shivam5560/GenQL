"""Orchestrates community detection, node embedding, and join-path mining
for one datasource's whole graph.

Depends only on ports; which concrete algorithm each port resolves to is a
composition-root and Settings concern, not this service's.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.node_embedder import NodeEmbedder


class GraphAnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    communities: int
    embedded_nodes: int
    join_paths: int


class GraphAnalysisService:
    def __init__(
        self,
        clustering: ClusteringAlgorithm,
        embedder: NodeEmbedder,
        miner: JoinPathMiner,
        join_path_writer: JoinPathWriter,
    ) -> None:
        self._clustering = clustering
        self._embedder = embedder
        self._miner = miner
        self._join_path_writer = join_path_writer

    def analyze(self, datasource_name: str) -> GraphAnalysisReport:
        communities = self._clustering.detect(datasource_name)
        embedded_nodes = self._embedder.embed(datasource_name)
        paths = self._miner.mine(datasource_name)
        written = self._join_path_writer.write(paths)
        return GraphAnalysisReport(
            communities=communities, embedded_nodes=embedded_nodes, join_paths=written
        )
