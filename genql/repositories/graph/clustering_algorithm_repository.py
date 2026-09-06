"""Leiden community detection, written back onto :Object nodes."""

from __future__ import annotations

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS


@CLUSTERING_ALGORITHMS.register("leiden")
class LeidenClusteringAlgorithm:
    def __init__(self, gds_provider: GdsClientProvider) -> None:
        self._gds_provider = gds_provider

    def detect(self, datasource_name: str) -> int:
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            result = self._gds_provider.client().leiden.write(  # type: ignore[attr-defined]
                graph, writeProperty="community_id"
            )
        return int(result["communityCount"])
