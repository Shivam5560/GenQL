"""Multi-turn providers: the three new stage services, the checkpointer, the
per-thread lock factory, and the graph rebuilt over all eight stages.

Its own container rather than more lines in QueryContainer, matching the
split-by-bounded-context convention the rest of genql/composition/ follows and
keeping both files well under the per-file line cap.

`query_graph` is deliberately re-declared here, overriding QueryContainer's
five-node version. Declarative containers resolve the most-derived declaration,
so every consumer — the CLI included — gets the eight-node graph with the
checkpointer attached, and there is exactly one graph provider in play rather
than two that could drift.

checkpoint_dsn is derived from settings.semantic_dsn rather than being its own
setting. GenQL's own database is singular; a second setting for it would let
the checkpointer and the semantic store point at different servers, and a
paused turn would then simply never be found again.
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
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.query_container import QueryContainer
from genql.infrastructure.checkpoint.postgres_checkpointer import build_checkpointer
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn
from genql.infrastructure.query.thread_lock_factory import PostgresThreadLockFactory
from genql.services.query.ambiguity_gate_service import AmbiguityGateService
from genql.services.query.domain_scoping_service import DomainScopingService
from genql.services.query.intent_classification_service import IntentClassificationService


class TurnContainer(QueryContainer):
    intent_classification_service = providers.Singleton(
        IntentClassificationService, chat=QueryContainer.chat_provider
    )
    ambiguity_gate_service = providers.Singleton(
        AmbiguityGateService,
        chat=QueryContainer.chat_provider,
        rules=QueryContainer.rule_reader,
        threshold=QueryContainer.settings.provided.ambiguity_threshold,
    )
    domain_scoping_service = providers.Singleton(
        DomainScopingService,
        retrieval=QueryContainer.retrieval_service,
        domains=QueryContainer.domain_repository,
        sample_size=QueryContainer.settings.provided.domain_scoping_sample_size,
    )

    checkpoint_dsn = providers.Callable(to_libpq_dsn, QueryContainer.settings.provided.semantic_dsn)
    # Singleton, so PostgresSaver.setup() runs once, lazily, the first time a
    # turn actually needs the graph — never on `genql --help`.
    checkpointer = providers.Singleton(
        build_checkpointer,
        dsn=checkpoint_dsn,
        max_size=QueryContainer.settings.provided.checkpoint_pool_max_size,
    )
    # A separate connection from the checkpointer's pool, on purpose:
    # pg_advisory_lock is session-scoped, and sharing the pool would deadlock
    # — the checkpointer needs a connection to write the checkpoint the lock
    # is protecting.
    thread_lock_factory = providers.Singleton(PostgresThreadLockFactory, dsn=checkpoint_dsn)

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(AmbiguityGateNode, gate=ambiguity_gate_service),
        domain_scoping=providers.Singleton(DomainScopingNode, scoper=domain_scoping_service),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=QueryContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=QueryContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=QueryContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=QueryContainer.static_validation_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=QueryContainer.guarded_execution_service
        ),
        checkpointer=checkpointer,
    )
