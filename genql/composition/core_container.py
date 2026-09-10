"""The base layer of the composition root: settings, GenQL's own semantic-store
engine, warehouse-facing catalog/profile repositories, and the datasource and
schema-registration services built directly from them. Every other container
in `genql/composition/` inherits from this one.
"""

from __future__ import annotations

import os

from dependency_injector import containers, providers

import genql.repositories.warehouse  # noqa: F401 - registration side effect
import genql.services.scope  # noqa: F401 - registration side effect
from genql.core.settings import Settings
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.ports.scope_resolver import ScopeResolver
from genql.infrastructure.auth.fernet_secret_cipher import FernetSecretCipher
from genql.infrastructure.catalog.catalog_reader_factory import CatalogReaderFactoryImpl
from genql.infrastructure.catalog.profile_reader_factory import ProfileReaderFactoryImpl
from genql.infrastructure.db.dsn_schemes import DSN_SCHEMES
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository
from genql.repositories.semantic.join_path_writer_repository import (
    PostgresJoinPathWriterRepository,
)
from genql.repositories.semantic.profile_writer_repository import (
    PostgresProfileWriterRepository,
)
from genql.repositories.semantic.schema_registration_repository import (
    PostgresSchemaRegistrationRepository,
)
from genql.repositories.semantic.semantic_catalog_reader_repository import (
    PostgresSemanticCatalogReader,
)
from genql.repositories.warehouse.registry import CATALOG_READERS
from genql.services.datasource.datasource_service import DatasourceService
from genql.services.datasource.schema_registration_service import SchemaRegistrationService
from genql.services.discovery.catalog_scan_service import CatalogScanService
from genql.services.discovery.profiling_service import ProfilingService
from genql.services.scope.registry import SCOPE_RESOLVERS


def build_scope_resolver(
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


class CoreContainer(containers.DeclarativeContainer):
    settings = providers.Singleton(Settings)

    semantic_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.semantic_dsn
    )

    catalog_writer = providers.Singleton(PostgresCatalogWriterRepository, engine=semantic_engine)
    profile_writer = providers.Singleton(PostgresProfileWriterRepository, engine=semantic_engine)
    semantic_catalog_reader = providers.Singleton(
        PostgresSemanticCatalogReader, engine=semantic_engine
    )
    join_path_writer = providers.Singleton(PostgresJoinPathWriterRepository, engine=semantic_engine)

    secret_cipher = providers.Singleton(FernetSecretCipher, key=settings.provided.secret_key)

    engine_provider = providers.Singleton(
        DatasourceEngineProvider,
        env=os.environ,
        cipher=secret_cipher,
        readonly_password=settings.provided.readonly_db_password,
    )

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
        dsn_schemes=DSN_SCHEMES,
        cipher=secret_cipher,
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
        build_scope_resolver,
        key=settings.provided.scope_resolver,
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        default_datasource=settings.provided.default_datasource,
    )
