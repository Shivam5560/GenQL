"""Phase 7's providers: three repositories, four services, the rule factory,
and the graph rebuilt over twelve stages.

`query_graph` is re-declared here, overriding AmbiguityContainer's eleven-node
version, exactly the way AmbiguityContainer itself overrode TurnContainer's —
declarative containers resolve the most-derived declaration, so every consumer
gets the twelve-node graph and there is one graph provider in play rather than
two that could drift.

`rewrite_recording_service` is a Callable provider rather than a Singleton so
that it evaluates to None when `record_execution_actuals` is false. That is
the whole disabled-by-default mechanism: the node's constructor parameter
receives None, and its `is not None` check does the rest. Nothing else in the
graph changes shape between the two configurations.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.api.query_ambiguity_nodes import (
    AmbiguityProbingNode,
    CandidateSelectionNode,
    CritiqueNode,
)
from genql.api.query_graph import build_query_graph
from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.api.query_optimizer_nodes import RewriteAndCostGateNode
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.ambiguity_container import AmbiguityContainer
from genql.domain.ports.execution_actuals_reader import ExecutionActualsReader
from genql.domain.ports.rewrite_outcome_writer import RewriteOutcomeWriter
from genql.infrastructure.query.rewrite_rule_factory import RewriteRuleFactoryImpl
from genql.repositories.query.cost_estimator_repository import PostgresCostEstimator
from genql.repositories.query.index_recommender_repository import PostgresIndexRecommender
from genql.repositories.query.rewrite_outcome_repository import PostgresRewriteOutcomeWriter
from genql.services.query.index_recommendation_service import IndexRecommendationService
from genql.services.query.optimization_service import OptimizationService
from genql.services.query.query_decomposer import LlmQueryDecomposer
from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService


def _recorder_if_enabled(
    enabled: bool, actuals: ExecutionActualsReader, writer: RewriteOutcomeWriter
) -> RewriteOutcomeRecordingService | None:
    """None when recording is off, so GuardedExecutionNode's `is not None`
    check is the only place the switch is read at runtime."""
    if not enabled:
        return None
    return RewriteOutcomeRecordingService(actuals=actuals, writer=writer)


class OptimizerContainer(AmbiguityContainer):
    cost_estimator = providers.Singleton(
        PostgresCostEstimator,
        provider=AmbiguityContainer.engine_provider,
        datasources=AmbiguityContainer.datasource_repository,
    )
    rewrite_outcome_writer = providers.Singleton(
        PostgresRewriteOutcomeWriter,
        engine=AmbiguityContainer.semantic_engine,
        datasources=AmbiguityContainer.datasource_repository,
    )
    index_recommender = providers.Singleton(
        PostgresIndexRecommender, engine=AmbiguityContainer.semantic_engine
    )

    rewrite_rule_factory = providers.Singleton(RewriteRuleFactoryImpl)
    query_decomposer = providers.Singleton(
        LlmQueryDecomposer, chat=AmbiguityContainer.chat_provider
    )
    optimization_service = providers.Singleton(
        OptimizationService,
        rules=rewrite_rule_factory,
        estimator=cost_estimator,
        decomposer=query_decomposer,
        budget=AmbiguityContainer.settings.provided.cost_budget,
    )
    rewrite_recording_service = providers.Callable(
        _recorder_if_enabled,
        AmbiguityContainer.settings.provided.record_execution_actuals,
        cost_estimator,
        rewrite_outcome_writer,
    )
    index_recommendation_service = providers.Singleton(
        IndexRecommendationService,
        recommender=index_recommender,
        datasources=AmbiguityContainer.datasource_repository,
    )

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=AmbiguityContainer.intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(
            AmbiguityGateNode, gate=AmbiguityContainer.ambiguity_gate_service
        ),
        domain_scoping=providers.Singleton(
            DomainScopingNode, scoper=AmbiguityContainer.domain_scoping_service
        ),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=AmbiguityContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=AmbiguityContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=AmbiguityContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=AmbiguityContainer.static_validation_service
        ),
        critique=providers.Singleton(CritiqueNode, service=AmbiguityContainer.critique_service),
        ambiguity_probing=providers.Singleton(
            AmbiguityProbingNode, service=AmbiguityContainer.ambiguity_probing_service
        ),
        candidate_selection=providers.Singleton(
            CandidateSelectionNode, service=AmbiguityContainer.candidate_selection_service
        ),
        rewrite_and_cost_gate=providers.Singleton(
            RewriteAndCostGateNode, service=optimization_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode,
            service=AmbiguityContainer.guarded_execution_service,
            recorder=rewrite_recording_service,
        ),
        checkpointer=AmbiguityContainer.checkpointer,
    )
