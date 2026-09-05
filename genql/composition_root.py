"""The only place that constructs dependencies."""

from __future__ import annotations

from typing import Any

from dependency_injector import containers, providers

from genql.core.settings import Settings

# Imported for its registration side effect: every discovery step decorates
# itself into DISCOVERY_STEPS when genql.discovery.steps is imported. This is
# the one explicit place that import happens; the runner's step list below is
# built FROM the registry, not from a hardcoded list of step classes.
from genql.discovery import steps as _discovery_steps  # noqa: F401
from genql.discovery.registry import DISCOVERY_STEPS
from genql.discovery.runner import DiscoveryRunner
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)
from genql.repositories.semantic.profile_writer_repository import (
    PostgresProfileWriterRepository,
)
from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)
from genql.services.discovery.catalog_scan_service import CatalogScanService
from genql.services.discovery.profiling_service import ProfilingService


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


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(Settings)

    warehouse_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.warehouse_dsn
    )
    semantic_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.semantic_dsn
    )

    catalog_reader = providers.Singleton(PostgresCatalogReaderRepository, engine=warehouse_engine)
    catalog_writer = providers.Singleton(PostgresCatalogWriterRepository, engine=semantic_engine)
    profile_reader = providers.Singleton(PostgresProfileReaderRepository, engine=warehouse_engine)
    profile_writer = providers.Singleton(PostgresProfileWriterRepository, engine=semantic_engine)

    catalog_scan_service = providers.Singleton(
        CatalogScanService, reader=catalog_reader, writer=catalog_writer
    )
    profiling_service = providers.Factory(
        ProfilingService,
        catalog=catalog_reader,
        reader=profile_reader,
        writer=profile_writer,
    )

    # Every step name registered in DISCOVERY_STEPS must have an entry here so
    # its constructor can be injected with the service it needs. A step
    # registered without an entry fails fast (KeyError) at import time rather
    # than being silently dropped from the pipeline.
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": catalog_scan_service,
        "data_profiling": profiling_service,
    }

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
    )
