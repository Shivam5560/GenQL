"""Reads a warehouse catalog and persists it to the semantic store.

Depends only on ports. It cannot reach a database even by accident, which is
what makes the unit tests above possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.catalog_reader_factory import CatalogReaderFactory
from genql.domain.ports.catalog_writer import CatalogWriter
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.value_objects.schema_ref import SchemaRef


class CatalogScanReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects: int
    columns: int
    constraints: int

    @property
    def total(self) -> int:
        return self.objects + self.columns + self.constraints


class CatalogScanService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        readers: CatalogReaderFactory,
        writer: CatalogWriter,
    ) -> None:
        self._datasources = datasources
        self._readers = readers
        self._writer = writer

    def scan(self, ref: SchemaRef) -> CatalogScanReport:
        reader = self._readers.for_datasource(self._datasources.get(ref.datasource_name))
        return CatalogScanReport(
            objects=self._writer.write_objects(reader.read_objects(ref)),
            columns=self._writer.write_columns(reader.read_columns(ref)),
            constraints=self._writer.write_constraints(reader.read_constraints(ref)),
        )
