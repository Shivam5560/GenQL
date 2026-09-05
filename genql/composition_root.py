"""The only place that constructs dependencies."""

from __future__ import annotations

from dependency_injector import containers, providers

from genql.core.settings import Settings
from genql.discovery.runner import DiscoveryRunner
from genql.discovery.steps.catalog_scan_step import CatalogScanStep
from genql.discovery.steps.data_profiling_step import DataProfilingStep
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

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(
            providers.Factory(CatalogScanStep, service=catalog_scan_service),
            providers.Factory(DataProfilingStep, service=profiling_service),
        ),
    )
