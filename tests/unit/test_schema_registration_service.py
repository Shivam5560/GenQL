"""A schema is verified to exist in the warehouse before it is registered."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.datasource.schema_registration_service import SchemaRegistrationService

DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
REF = SchemaRef(datasource_name="local", schema_name="shop")


class FakeDatasources:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return DS

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [DS]

    def remove(self, name: str) -> None: ...


class FakeRegistrations:
    def __init__(self) -> None:
        self.rows: list[SchemaRegistration] = []

    def add(self, registration: SchemaRegistration) -> None:
        self.rows.append(registration)

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        for row in self.rows:
            if row.ref == ref:
                return row
        raise UnknownSchemaRegistrationError(ref.qualified_name, [])

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        return [r for r in self.rows if r.datasource_name == datasource_name]

    def remove(self, ref: SchemaRef) -> None:
        self.rows = [r for r in self.rows if r.ref != ref]

    def mark_discovered(self, ref: SchemaRef) -> None: ...


class FakeReader:
    def __init__(self, objects: list[DatabaseObject]) -> None:
        self._objects = objects

    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return self._objects

    def read_columns(self, ref: SchemaRef) -> Sequence[object]:
        return []

    def read_constraints(self, ref: SchemaRef) -> Sequence[object]:
        return []


class FakeFactory:
    def __init__(self, reader: FakeReader) -> None:
        self._reader = reader

    def for_datasource(self, datasource: Datasource) -> FakeReader:
        return self._reader


POPULATED = FakeReader(
    [
        DatabaseObject(
            datasource_name="local",
            schema_name="shop",
            object_name="customer",
            object_type=ObjectType.TABLE,
        )
    ]
)
EMPTY = FakeReader([])


def test_register_persists_a_schema_that_exists() -> None:
    registrations = FakeRegistrations()
    service = SchemaRegistrationService(FakeDatasources(), registrations, FakeFactory(POPULATED))

    created = service.register(REF, "the shop")

    assert created.ref == REF
    assert registrations.rows[0].description == "the shop"


def test_register_refuses_a_schema_the_warehouse_does_not_have() -> None:
    service = SchemaRegistrationService(FakeDatasources(), FakeRegistrations(), FakeFactory(EMPTY))

    with pytest.raises(UnknownSchemaRegistrationError, match="local.shop"):
        service.register(REF, None)


def test_remove_delegates_to_the_repository() -> None:
    registrations = FakeRegistrations()
    service = SchemaRegistrationService(FakeDatasources(), registrations, FakeFactory(POPULATED))
    service.register(REF, None)

    service.remove(REF)

    assert registrations.rows == []
