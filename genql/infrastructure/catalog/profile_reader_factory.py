"""Binds a ProfileReader to one datasource."""

from __future__ import annotations

import genql.repositories.warehouse  # noqa: F401 - registration side effect
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.profile_reader import ProfileReader
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.registry import PROFILE_READERS


class ProfileReaderFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> ProfileReader:
        engine = self._provider.engine_for(datasource)
        return PROFILE_READERS.create(datasource.dialect, engine=engine)
