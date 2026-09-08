"""Online query-path providers: the two read repositories, the five stage
services, the two per-datasource factories, and the compiled LangGraph graph.

Inherits SemanticContainer because schema linking reuses Phase 4's
retrieval_service and semantic_catalog_reader, and planning and generation
reuse its chat_provider — nothing in this phase introduces a second model
surface, per the parent spec's §21 stance that model choice is configuration.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.api.query_graph import build_query_graph
from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.composition.semantic_container import SemanticContainer
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl
from genql.infrastructure.query.query_executor_factory import QueryExecutorFactoryImpl
from genql.repositories.query.object_name_repository import PostgresObjectNameReader
from genql.repositories.semantic.join_path_reader_repository import PostgresJoinPathReader
from genql.services.query.candidate_generation_service import CandidateGenerationService
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.planning_service import PlanningService
from genql.services.query.schema_linking_service import SchemaLinkingService
from genql.services.query.static_validation_service import StaticValidationService


class QueryContainer(SemanticContainer):
    object_name_reader = providers.Singleton(
        PostgresObjectNameReader, engine=SemanticContainer.semantic_engine
    )
    join_path_reader = providers.Singleton(
        PostgresJoinPathReader, engine=SemanticContainer.semantic_engine
    )

    schema_linking_service = providers.Singleton(
        SchemaLinkingService,
        retrieval=SemanticContainer.retrieval_service,
        reader=SemanticContainer.semantic_catalog_reader,
        join_paths=join_path_reader,
        metrics=SemanticContainer.metric_repository,
        top_k=SemanticContainer.settings.provided.search_top_k,
    )
    planning_service = providers.Singleton(PlanningService, chat=SemanticContainer.chat_provider)
    candidate_generation_service = providers.Singleton(
        CandidateGenerationService,
        chat=SemanticContainer.chat_provider,
        escalation_chat=SemanticContainer.escalation_chat_provider,
        examples=SemanticContainer.ambiguity_example_reader,
        example_top_k=SemanticContainer.settings.provided.ambiguity_example_top_k,
    )

    guardrail_factory = providers.Singleton(
        GuardrailFactoryImpl,
        objects=object_name_reader,
        row_cap=SemanticContainer.settings.provided.query_row_cap,
        statement_timeout_ms=SemanticContainer.settings.provided.query_statement_timeout_ms,
    )
    static_validation_service = providers.Singleton(
        StaticValidationService, guardrails=guardrail_factory
    )

    query_executor_factory = providers.Singleton(
        QueryExecutorFactoryImpl,
        provider=SemanticContainer.engine_provider,
        statement_timeout_ms=SemanticContainer.settings.provided.query_statement_timeout_ms,
    )
    guarded_execution_service = providers.Singleton(
        GuardedExecutionService,
        datasources=SemanticContainer.datasource_repository,
        executors=query_executor_factory,
        row_cap=SemanticContainer.settings.provided.query_row_cap,
    )

    query_graph = providers.Singleton(
        build_query_graph,
        schema_linking=providers.Singleton(SchemaLinkingNode, linker=schema_linking_service),
        planning=providers.Singleton(PlanningNode, planner=planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=static_validation_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=guarded_execution_service
        ),
    )
