"""The only place that constructs dependencies.

The bulk of the wiring lives in `genql/composition/`, split by bounded
context (core/graph/gateway/semantic/query/turn/ambiguity/optimizer) to stay under the project's
per-file line cap. `Container` here is the single inheritance point every
consumer imports; it only adds the piece that spans every discovery step: the
step-to-service map and the runner built from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dependency_injector import providers

from genql.composition.auth_container import AuthContainer
from genql.core.settings import Settings

# Imported for its registration side effect: every discovery step decorates
# itself into DISCOVERY_STEPS when genql.discovery.steps is imported. This is
# the one explicit place that import happens; the runner's step list below is
# built FROM the registry, not from a hardcoded list of step classes.
from genql.discovery import steps as _discovery_steps  # noqa: F401
from genql.discovery.registry import DISCOVERY_STEPS
from genql.discovery.runner import DiscoveryRunner
from genql.infrastructure.ingestion.file_overlay_loader import FileOverlayLoader
from genql.infrastructure.ingestion.system_clock import SystemClock
from genql.infrastructure.ingestion.worker import IngestionWorker
from genql.repositories.semantic.ingestion_job_repository import (
    PostgresIngestionJobRepository,
)
from genql.services.datasource.ingestion_service import IngestionService
from genql.services.datasource.onboarding_service import OnboardingService


def _step_providers_in_registered_order(
    service_providers: dict[str, providers.Provider[Any]],
) -> list[providers.Provider[Any]]:
    """Build one Factory provider per registered step, in DISCOVERY_STEPS order.

    A plain function (rather than a class-body comprehension) because names
    assigned in a class body are not visible inside a nested comprehension's
    scope — this keeps the lookup working and keeps it obviously correct.
    """
    return [
        providers.Factory(DISCOVERY_STEPS.get(name), service=service_providers[name])
        for name in DISCOVERY_STEPS.keys()  # noqa: SIM118 - Registry, not a dict
    ]


class Container(AuthContainer):
    # Every step name registered in DISCOVERY_STEPS must have an entry here so
    # its constructor can be injected with the service it needs. A step
    # registered without an entry fails fast (KeyError) at import time rather
    # than being silently dropped from the pipeline.
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": AuthContainer.catalog_scan_service,
        "data_profiling": AuthContainer.profiling_service,
        "graph_projection": AuthContainer.graph_projection_service,
        "object_profiling": AuthContainer.object_profiling_service,
        "synthetic_ambiguity_log": AuthContainer.synthetic_ambiguity_log_service,
    }

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
        registrations=AuthContainer.schema_registration_repository,
    )

    # ---- datasource onboarding -----------------------------------------
    # Wired here rather than in a bounded-context container because this is
    # the one seam that needs `discovery_runner`, and `discovery_runner` is
    # built from the step registry directly above.

    clock = providers.Singleton(SystemClock)

    ingestion_job_repository = providers.Singleton(
        PostgresIngestionJobRepository, engine=AuthContainer.semantic_engine
    )

    overlay_loader = providers.Singleton(
        FileOverlayLoader,
        root=providers.Factory(Path, AuthContainer.settings.provided.semantic_overlay_dir),
    )

    ingestion_service = providers.Factory(
        IngestionService,
        schemas=AuthContainer.schema_registration_service,
        discovery=discovery_runner,
        overlays=overlay_loader,
        overlay_service=AuthContainer.semantic_overlay_service,
        compiler=AuthContainer.compile_service,
        graph=AuthContainer.graph_analysis_service,
        domains=AuthContainer.domain_discovery_service,
        clock=clock,
        sample_limit=AuthContainer.settings.provided.profile_sample_limit,
    )

    onboarding_service = providers.Singleton(
        OnboardingService,
        datasources=AuthContainer.datasource_service,
        datasource_repository=AuthContainer.datasource_repository,
        jobs=ingestion_job_repository,
        clock=clock,
    )

    ingestion_worker = providers.Singleton(
        IngestionWorker,
        jobs=ingestion_job_repository,
        # `.provider` injects the factory itself, not one built instance: the
        # worker builds a fresh IngestionService per job, so a long-lived
        # worker never holds a stale collaborator graph.
        ingestion=ingestion_service.provider,
        poll_seconds=AuthContainer.settings.provided.ingestion_poll_seconds,
        stale_after_seconds=AuthContainer.settings.provided.ingestion_stale_after_seconds,
    )

    @classmethod
    def with_overrides(cls, **fields: object) -> Container:
        """A container whose Settings carry the given field values.

        The whole ablation mechanism. A pre-built Settings passed through
        providers.Object rather than dependency_injector's override() machinery:
        one line, obviously correct, and independent of override-reset semantics
        across seven inherited container classes.

        Unknown fields raise rather than being ignored, because a typo'd
        override switches nothing off and the resulting "no delta" reads as a
        finding about the architecture rather than as a bug in the harness.
        """
        unknown = sorted(set(fields) - set(Settings.model_fields))
        if unknown:
            raise ValueError(f"unknown settings field(s): {', '.join(unknown)}")

        container = cls()
        base = container.settings()
        container.settings.override(providers.Object(base.model_copy(update=dict(fields))))
        return container
