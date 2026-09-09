"""Leiden community detection, written back onto :Object nodes."""

from __future__ import annotations

from neo4j.exceptions import DriverError, Neo4jError

from genql.domain.errors import GraphAnalysisError
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import (
    UNDIRECTED_RELATIONSHIP_TYPE,
    GraphCatalogSession,
)
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS


@CLUSTERING_ALGORITHMS.register("leiden")
class LeidenClusteringAlgorithm:
    def __init__(self, gds_provider: GdsClientProvider) -> None:
        self._gds_provider = gds_provider

    def detect(self, datasource_name: str) -> int:
        try:
            with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
                result = self._gds_provider.client().leiden.write(  # type: ignore[attr-defined]
                    graph,
                    writeProperty="community_id",
                    relationshipTypes=[UNDIRECTED_RELATIONSHIP_TYPE],
                )
        except (Neo4jError, DriverError) as exc:
            raise GraphAnalysisError(
                f"failed to detect communities for {datasource_name!r}: {exc}"
            ) from exc
        return int(result["communityCount"])
