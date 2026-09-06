"""FastRP topology-aware node embeddings, written back onto :Object nodes."""

from __future__ import annotations

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import NODE_EMBEDDERS

_EMBEDDING_DIMENSION = 128


@NODE_EMBEDDERS.register("fastrp")
class FastRpNodeEmbedder:
    def __init__(self, gds_provider: GdsClientProvider) -> None:
        self._gds_provider = gds_provider

    def embed(self, datasource_name: str) -> int:
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            result = self._gds_provider.client().fastRP.write(  # type: ignore[attr-defined]
                graph, writeProperty="embedding", embeddingDimension=_EMBEDDING_DIMENSION
            )
        return int(result["nodePropertiesWritten"])
