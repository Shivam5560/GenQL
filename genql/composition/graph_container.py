"""Graph-layer providers: the Neo4j driver, GDS-backed clustering/embedding/
join-path algorithms (resolved through their registries by `Settings`-named
key), and the services built from them.
"""

from __future__ import annotations

from dependency_injector import providers
from neo4j import Driver

import genql.repositories.graph  # noqa: F401 - registration side effect
from genql.composition.core_container import CoreContainer
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.node_embedder import NodeEmbedder
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.cluster_reader_repository import Neo4jClusterReader
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.registry import (
    CLUSTERING_ALGORITHMS,
    JOIN_PATH_STRATEGIES,
    NODE_EMBEDDERS,
)
from genql.services.graph.graph_analysis_service import GraphAnalysisService
from genql.services.graph.graph_projection_service import GraphProjectionService


def build_clustering_algorithm(key: str, gds_provider: GdsClientProvider) -> ClusteringAlgorithm:
    return CLUSTERING_ALGORITHMS.create(key, gds_provider=gds_provider)


def build_node_embedder(key: str, gds_provider: GdsClientProvider) -> NodeEmbedder:
    return NODE_EMBEDDERS.create(key, gds_provider=gds_provider)


def build_join_path_miner(
    key: str, driver: Driver, gds_provider: GdsClientProvider, max_hops: int
) -> JoinPathMiner:
    return JOIN_PATH_STRATEGIES.create(
        key, driver=driver, gds_provider=gds_provider, max_hops=max_hops
    )


class GraphContainer(CoreContainer):
    neo4j_driver = providers.Singleton(
        create_neo4j_driver,
        uri=CoreContainer.settings.provided.neo4j_uri,
        user=CoreContainer.settings.provided.neo4j_user,
        password=CoreContainer.settings.provided.neo4j_password,
    )

    graph_writer = providers.Singleton(Neo4jGraphWriterRepository, driver=neo4j_driver)
    graph_projection_service = providers.Factory(
        GraphProjectionService,
        reader=CoreContainer.semantic_catalog_reader,
        writer=graph_writer,
    )

    cluster_reader = providers.Singleton(Neo4jClusterReader, driver=neo4j_driver)

    gds_client_provider = providers.Singleton(GdsClientProvider, driver=neo4j_driver)

    clustering_algorithm = providers.Singleton(
        build_clustering_algorithm,
        key=CoreContainer.settings.provided.clustering_algorithm,
        gds_provider=gds_client_provider,
    )
    node_embedder = providers.Singleton(
        build_node_embedder,
        key=CoreContainer.settings.provided.node_embedding_algorithm,
        gds_provider=gds_client_provider,
    )
    join_path_miner = providers.Singleton(
        build_join_path_miner,
        key=CoreContainer.settings.provided.join_path_strategy,
        driver=neo4j_driver,
        gds_provider=gds_client_provider,
        max_hops=CoreContainer.settings.provided.max_join_path_hops,
    )

    graph_analysis_service = providers.Singleton(
        GraphAnalysisService,
        clustering=clustering_algorithm,
        embedder=node_embedder,
        miner=join_path_miner,
        join_path_writer=CoreContainer.join_path_writer,
    )
