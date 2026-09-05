"""Profiles every column of a schema.

One unprofilable column must not lose the other four hundred, so failures are
collected and reported rather than raised.
"""

from __future__ import annotations

import structlog

from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.errors import ProfilingError
from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.profile_reader import ProfileReader
from genql.domain.ports.profile_writer import ProfileWriter

_log = structlog.get_logger(__name__)


class ProfilingService:
    def __init__(
        self, catalog: CatalogReader, reader: ProfileReader, writer: ProfileWriter
    ) -> None:
        self._catalog = catalog
        self._reader = reader
        self._writer = writer
        self.skipped: list[str] = []

    def profile(self, schema: str, sample_limit: int) -> int:
        self.skipped = []
        profiles: list[ColumnProfile] = []
        for column in self._catalog.read_columns(schema):
            try:
                profiles.append(self._reader.profile_column(column, sample_limit))
            except ProfilingError as exc:
                self.skipped.append(exc.qualified_name)
                _log.warning("profiling.skipped", column=exc.qualified_name, reason=str(exc))
        return self._writer.write_profiles(profiles)
