"""Binds a CatalogReader to one datasource.

Importing `genql.repositories.warehouse` is what populates CATALOG_READERS:
the package imports each reader module for its registration decorator.
"""

from __future__ import annotations

import genql.repositories.warehouse  # noqa: F401 - registration side effect
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.catalog_reader import CatalogReader
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.registry import CATALOG_READERS


class CatalogReaderFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> CatalogReader:
        engine = self._provider.engine_for(datasource)
        return CATALOG_READERS.create(datasource.dialect, engine=engine)
