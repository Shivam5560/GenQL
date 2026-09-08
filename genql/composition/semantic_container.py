"""Semantic-store providers: enrichment/domain/metric repositories, the
domain-discovery and semantic-overlay services, the search-document compiler
and compile service, and retrieval. Needs both the graph layer (Neo4j driver,
clustering) and the gateway layer (chat/embedding/rerank providers), so it
inherits from both.
"""

from __future__ import annotations

from dependency_injector import providers
from neo4j import Driver

import genql.repositories.semantic  # noqa: F401 - registration side effect
from genql.composition.gateway_container import GatewayContainer
from genql.composition.graph_container import GraphContainer
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.retriever import Retriever
from genql.infrastructure.catalog.comment_writer_factory import CommentWriterFactoryImpl
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS
from genql.repositories.semantic.ambiguity_example_repository import (
    PostgresAmbiguityExampleWriter,
)
from genql.repositories.semantic.domain_namer_repository import LlmDomainNamer
from genql.repositories.semantic.domain_repository import PostgresDomainRepository
from genql.repositories.semantic.enrichment_repository import PostgresEnrichmentRepository
from genql.repositories.semantic.metric_repository import PostgresMetricRepository
from genql.repositories.semantic.registry import ENRICHERS, RETRIEVERS
from genql.repositories.semantic.rule_repository import PostgresRuleReader, PostgresRuleWriter
from genql.repositories.semantic.search_document_repository import SearchDocumentCompiler
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService
from genql.services.semantic.compile_service import CompileService
from genql.services.semantic.domain_discovery_service import DomainDiscoveryService
from genql.services.semantic.object_profiling_service import ObjectProfilingService
from genql.services.semantic.retrieval_service import RetrievalService
from genql.services.semantic.semantic_overlay_service import SemanticOverlayService


def build_domain_clustering_algorithm(
    key: str, driver: Driver, enrichment_reader: EnrichmentReader, k_min: int, k_max: int
) -> object:
    return CLUSTERING_ALGORITHMS.create(
        key, driver=driver, enrichment_reader=enrichment_reader, k_min=k_min, k_max=k_max
    )


def build_retriever(key: str, engine: object, rrf_k: int) -> Retriever:
    if key == "hybrid_rrf":
        return RETRIEVERS.create(key, engine=engine, rrf_k=rrf_k)
    if key == "domain_scoped":
        inner = RETRIEVERS.create("hybrid_rrf", engine=engine, rrf_k=rrf_k)
        return RETRIEVERS.create(key, inner=inner)
    return RETRIEVERS.create(key, engine=engine)


def build_enrichers() -> list[Enricher]:
    return [ENRICHERS.create(key) for key in ENRICHERS.keys()]  # noqa: SIM118 - Registry, not a dict


class SemanticContainer(GraphContainer, GatewayContainer):
    enrichment_repository = providers.Singleton(
        PostgresEnrichmentRepository, engine=GraphContainer.semantic_engine
    )
    domain_repository = providers.Singleton(
        PostgresDomainRepository, engine=GraphContainer.semantic_engine
    )
    metric_repository = providers.Singleton(
        PostgresMetricRepository, engine=GraphContainer.semantic_engine
    )
    rule_reader = providers.Singleton(PostgresRuleReader, engine=GraphContainer.semantic_engine)
    rule_writer = providers.Singleton(PostgresRuleWriter, engine=GraphContainer.semantic_engine)

    object_profiling_service = providers.Factory(
        ObjectProfilingService,
        reader=GraphContainer.semantic_catalog_reader,
        chat=GatewayContainer.chat_provider,
        embedder=GatewayContainer.embedding_provider,
        writer=enrichment_repository,
    )

    ambiguity_example_writer = providers.Singleton(
        PostgresAmbiguityExampleWriter,
        engine=GraphContainer.semantic_engine,
        embedder=GatewayContainer.embedding_provider,
    )
    synthetic_ambiguity_log_service = providers.Factory(
        SyntheticAmbiguityLogService,
        chat=GatewayContainer.chat_provider,
        embedder=GatewayContainer.embedding_provider,
        domains=domain_repository,
        metrics=metric_repository,
        writer=ambiguity_example_writer,
    )

    domain_clustering_algorithm = providers.Singleton(
        build_domain_clustering_algorithm,
        key=GraphContainer.settings.provided.domain_clustering_algorithm,
        driver=GraphContainer.neo4j_driver,
        enrichment_reader=enrichment_repository,
        k_min=GraphContainer.settings.provided.domain_cluster_k_min,
        k_max=GraphContainer.settings.provided.domain_cluster_k_max,
    )
    domain_namer = providers.Singleton(LlmDomainNamer, chat=GatewayContainer.chat_provider)
    domain_discovery_service = providers.Singleton(
        DomainDiscoveryService,
        clustering=domain_clustering_algorithm,
        cluster_reader=GraphContainer.cluster_reader,
        enrichment_reader=enrichment_repository,
        namer=domain_namer,
        domain_writer=domain_repository,
    )

    semantic_overlay_service = providers.Singleton(
        SemanticOverlayService,
        enrichment_reader=enrichment_repository,
        enrichment_writer=enrichment_repository,
        metric_writer=metric_repository,
        rule_writer=rule_writer,
        join_path_writer=GraphContainer.join_path_writer,
        enrichers=providers.Factory(build_enrichers),
    )

    comment_writer_factory = providers.Singleton(
        CommentWriterFactoryImpl, provider=GraphContainer.engine_provider
    )
    search_document_compiler = providers.Singleton(
        SearchDocumentCompiler,
        engine=GraphContainer.semantic_engine,
        embedder=GatewayContainer.embedding_provider,
    )
    compile_service = providers.Singleton(
        CompileService,
        search_document_writer=search_document_compiler,
        enrichment_reader=enrichment_repository,
        comment_writer_factory=comment_writer_factory,
        datasource_repository=GraphContainer.datasource_repository,
    )

    retriever = providers.Singleton(
        build_retriever,
        key=GraphContainer.settings.provided.retriever,
        engine=GraphContainer.semantic_engine,
        rrf_k=GraphContainer.settings.provided.rrf_k,
    )
    retrieval_service = providers.Singleton(
        RetrievalService,
        embedder=GatewayContainer.embedding_provider,
        retriever=retriever,
        rerank=GatewayContainer.rerank_provider,
    )
