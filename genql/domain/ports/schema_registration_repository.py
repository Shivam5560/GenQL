"""Reads and writes the schemas GenQL has been told to manage."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class SchemaRegistrationRepository(Protocol):
    def add(self, registration: SchemaRegistration) -> None: ...

    def get(self, ref: SchemaRef) -> SchemaRegistration: ...

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]: ...

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None: ...
