"""Registers, lists, and removes managed schemas.

Registration reads the datasource's catalog first. A typo in a schema name
would otherwise register happily and then discover nothing, which is a much
worse failure than being refused here.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.ports.catalog_reader_factory import CatalogReaderFactory
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.schema_ref import SchemaRef


class SchemaRegistrationService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        readers: CatalogReaderFactory,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations
        self._readers = readers

    def register(self, ref: SchemaRef, description: str | None) -> SchemaRegistration:
        reader = self._readers.for_datasource(self._datasources.get(ref.datasource_name))
        if not reader.read_objects(ref):
            raise UnknownSchemaRegistrationError(ref.qualified_name, [])
        registration = SchemaRegistration(
            datasource_name=ref.datasource_name,
            schema_name=ref.schema_name,
            description=description,
        )
        self._registrations.add(registration)
        return registration

    def list_for_datasource(self, datasource_name: str) -> Sequence[SchemaRegistration]:
        return self._registrations.list_for_datasource(datasource_name)

    def remove(self, ref: SchemaRef) -> None:
        self._registrations.remove(ref)
