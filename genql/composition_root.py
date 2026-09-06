"""The only place that constructs dependencies."""

from __future__ import annotations

import os
from typing import Any

from dependency_injector import containers, providers

import genql.repositories.warehouse  # noqa: F401 - registration side effect
import genql.services.scope  # noqa: F401 - registration side effect
from genql.core.settings import Settings

# Imported for its registration side effect: every discovery step decorates
# itself into DISCOVERY_STEPS when genql.discovery.steps is imported. This is
# the one explicit place that import happens; the runner's step list below is
# built FROM the registry, not from a hardcoded list of step classes.
from genql.discovery import steps as _discovery_steps  # noqa: F401
from genql.discovery.registry import DISCOVERY_STEPS
from genql.discovery.runner import DiscoveryRunner
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.ports.scope_resolver import ScopeResolver
from genql.infrastructure.catalog.catalog_reader_factory import CatalogReaderFactoryImpl
from genql.infrastructure.catalog.profile_reader_factory import ProfileReaderFactoryImpl
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository
from genql.repositories.semantic.profile_writer_repository import (
    PostgresProfileWriterRepository,
)
from genql.repositories.semantic.schema_registration_repository import (
    PostgresSchemaRegistrationRepository,
)
from genql.repositories.warehouse.registry import CATALOG_READERS
from genql.services.datasource.datasource_service import DatasourceService
from genql.services.datasource.schema_registration_service import SchemaRegistrationService
from genql.services.discovery.catalog_scan_service import CatalogScanService
from genql.services.discovery.profiling_service import ProfilingService
from genql.services.scope.registry import SCOPE_RESOLVERS


def _build_scope_resolver(
    key: str,
    datasources: DatasourceRepository,
    registrations: SchemaRegistrationRepository,
    default_datasource: str | None,
) -> ScopeResolver:
    return SCOPE_RESOLVERS.create(
        key,
        datasources=datasources,
        registrations=registrations,
        default_datasource=default_datasource,
    )


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

    semantic_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.semantic_dsn
    )

    catalog_writer = providers.Singleton(PostgresCatalogWriterRepository, engine=semantic_engine)
    profile_writer = providers.Singleton(PostgresProfileWriterRepository, engine=semantic_engine)

    engine_provider = providers.Singleton(DatasourceEngineProvider, env=os.environ)

    datasource_repository = providers.Singleton(
        PostgresDatasourceRepository, engine=semantic_engine
    )
    schema_registration_repository = providers.Singleton(
        PostgresSchemaRegistrationRepository, engine=semantic_engine
    )

    catalog_reader_factory = providers.Singleton(CatalogReaderFactoryImpl, provider=engine_provider)
    profile_reader_factory = providers.Singleton(ProfileReaderFactoryImpl, provider=engine_provider)

    catalog_scan_service = providers.Singleton(
        CatalogScanService,
        datasources=datasource_repository,
        readers=catalog_reader_factory,
        writer=catalog_writer,
    )
    profiling_service = providers.Factory(
        ProfilingService,
        datasources=datasource_repository,
        catalog_readers=catalog_reader_factory,
        profile_readers=profile_reader_factory,
        writer=profile_writer,
    )

    datasource_service = providers.Singleton(
        DatasourceService,
        datasources=datasource_repository,
        dialects=providers.Callable(CATALOG_READERS.keys),
        dialect_registry=CATALOG_READERS.name,
        env=os.environ,
        engines=engine_provider,
    )
    schema_registration_service = providers.Singleton(
        SchemaRegistrationService,
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        readers=catalog_reader_factory,
    )

    scope_resolver = providers.Singleton(
        _build_scope_resolver,
        key=settings.provided.scope_resolver,
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        default_datasource=settings.provided.default_datasource,
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
        registrations=schema_registration_repository,
    )
