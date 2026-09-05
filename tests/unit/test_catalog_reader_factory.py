"""The factory picks an implementation by dialect and binds it to an engine."""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.infrastructure.catalog.catalog_reader_factory import CatalogReaderFactoryImpl
from genql.infrastructure.catalog.profile_reader_factory import ProfileReaderFactoryImpl
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.registries.errors import UnknownRegistryKeyError

POSTGRES = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
UNSUPPORTED = Datasource(name="odd", dialect="db2", dsn_env_var="GENQL_WAREHOUSE_DSN")
ENV = {"GENQL_WAREHOUSE_DSN": "postgresql+psycopg://u:p@host/db"}


class FakeEngine:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


@pytest.fixture()
def provider() -> DatasourceEngineProvider:
    return DatasourceEngineProvider(env=ENV, engine_factory=FakeEngine)  # type: ignore[arg-type]


def test_postgres_dialect_yields_the_postgres_catalog_reader(
    provider: DatasourceEngineProvider,
) -> None:
    reader = CatalogReaderFactoryImpl(provider=provider).for_datasource(POSTGRES)

    assert type(reader).__name__ == "PostgresCatalogReaderRepository"


def test_postgres_dialect_yields_the_postgres_profile_reader(
    provider: DatasourceEngineProvider,
) -> None:
    reader = ProfileReaderFactoryImpl(provider=provider).for_datasource(POSTGRES)

    assert type(reader).__name__ == "PostgresProfileReaderRepository"


def test_an_unregistered_dialect_raises_and_names_what_is_available(
    provider: DatasourceEngineProvider,
) -> None:
    factory = CatalogReaderFactoryImpl(provider=provider)

    with pytest.raises(UnknownRegistryKeyError, match="postgres"):
        factory.for_datasource(UNSUPPORTED)
