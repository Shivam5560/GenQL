"""Binds a CommentWriter to one datasource's warehouse engine — mirrors
CatalogReaderFactoryImpl exactly, including dialect dispatch through the
registry: adding a new dialect's comment writer is one file plus one
decorator, not an edit here.
"""

from __future__ import annotations

import genql.repositories.warehouse  # noqa: F401 - registration side effect
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.comment_writer import CommentWriter
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.registry import COMMENT_WRITERS


class CommentWriterFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> CommentWriter:
        engine = self._provider.engine_for(datasource)
        return COMMENT_WRITERS.create(datasource.dialect, engine=engine)
