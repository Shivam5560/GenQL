"""Ambiguity-machinery providers: the three new stage services and the graph
rebuilt over all eleven stages.

`query_graph` is re-declared here, overriding TurnContainer's eight-node
version, exactly the way TurnContainer itself overrode QueryContainer's five-
node version in Phase 6 — declarative containers resolve the most-derived
declaration, so every consumer gets the eleven-node graph with no risk of two
graph providers drifting apart.
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
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.turn_container import TurnContainer
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService
from genql.services.query.candidate_selection_service import CandidateSelectionService
from genql.services.query.critique_service import CritiqueService
from genql.services.query.probe_designer import LlmProbeDesigner


class AmbiguityContainer(TurnContainer):
    critique_service = providers.Singleton(CritiqueService, chat=TurnContainer.chat_provider)
    probe_designer = providers.Singleton(LlmProbeDesigner, chat=TurnContainer.chat_provider)
    ambiguity_probing_service = providers.Singleton(
        AmbiguityProbingService,
        designer=probe_designer,
        validation=TurnContainer.static_validation_service,
        execution=TurnContainer.guarded_execution_service,
        max_probes=TurnContainer.settings.provided.probing_max_probes,
    )
    candidate_selection_service = providers.Singleton(CandidateSelectionService)

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=TurnContainer.intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(
            AmbiguityGateNode,
            gate=TurnContainer.ambiguity_gate_service,
            contested_min_resolved=TurnContainer.settings.provided.contested_min_resolved_dimensions,
        ),
        domain_scoping=providers.Singleton(
            DomainScopingNode, scoper=TurnContainer.domain_scoping_service
        ),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=TurnContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=TurnContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=TurnContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=TurnContainer.static_validation_service
        ),
        critique=providers.Singleton(CritiqueNode, service=critique_service),
        ambiguity_probing=providers.Singleton(
            AmbiguityProbingNode,
            service=ambiguity_probing_service,
            skip_margin=TurnContainer.settings.provided.probing_skip_margin,
        ),
        candidate_selection=providers.Singleton(
            CandidateSelectionNode, service=candidate_selection_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=TurnContainer.guarded_execution_service
        ),
        checkpointer=TurnContainer.checkpointer,
    )
