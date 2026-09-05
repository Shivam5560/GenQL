"""Profiles every column of a schema.

One unprofilable column must not lose the other four hundred, so failures are
collected and reported rather than raised.
"""

from __future__ import annotations

import structlog

from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.errors import ProfilingError
from genql.domain.ports.catalog_reader_factory import CatalogReaderFactory
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.profile_reader_factory import ProfileReaderFactory
from genql.domain.ports.profile_writer import ProfileWriter
from genql.domain.value_objects.schema_ref import SchemaRef

_log = structlog.get_logger(__name__)


class ProfilingService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        catalog_readers: CatalogReaderFactory,
        profile_readers: ProfileReaderFactory,
        writer: ProfileWriter,
    ) -> None:
        self._datasources = datasources
        self._catalog_readers = catalog_readers
        self._profile_readers = profile_readers
        self._writer = writer
        self.skipped: list[str] = []

    def profile(self, ref: SchemaRef, sample_limit: int) -> int:
        self.skipped = []
        datasource = self._datasources.get(ref.datasource_name)
        catalog = self._catalog_readers.for_datasource(datasource)
        reader = self._profile_readers.for_datasource(datasource)
        profiles: list[ColumnProfile] = []
        for column in catalog.read_columns(ref):
            try:
                profiles.append(reader.profile_column(column, sample_limit))
            except ProfilingError as exc:
                self.skipped.append(exc.qualified_name)
                _log.warning("profiling.skipped", column=exc.qualified_name, reason=str(exc))
        return self._writer.write_profiles(profiles)
