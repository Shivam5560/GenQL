"""Reads a warehouse catalog and persists it to the semantic store.

Depends only on ports. It cannot reach a database even by accident, which is
what makes the unit tests above possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.catalog_writer import CatalogWriter


class CatalogScanReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects: int
    columns: int
    constraints: int

    @property
    def total(self) -> int:
        return self.objects + self.columns + self.constraints


class CatalogScanService:
    def __init__(self, reader: CatalogReader, writer: CatalogWriter) -> None:
        self._reader = reader
        self._writer = writer

    def scan(self, schema: str) -> CatalogScanReport:
        return CatalogScanReport(
            objects=self._writer.write_objects(self._reader.read_objects(schema)),
            columns=self._writer.write_columns(self._reader.read_columns(schema)),
            constraints=self._writer.write_constraints(self._reader.read_constraints(schema)),
        )
