"""Reads structural metadata from the target warehouse.

Methods take a SchemaRef rather than a schema string: the reader is already
bound to one datasource by its factory, but it needs the datasource NAME to
stamp onto the entities it returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class CatalogReader(Protocol):
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]: ...

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]: ...

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]: ...
