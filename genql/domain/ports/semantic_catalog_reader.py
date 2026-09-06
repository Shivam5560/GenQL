"""Reads structural metadata back out of GenQL's own semantic store.

The missing read side of CatalogWriter. This is what lets graph projection
run from Postgres alone, independent of a live discovery run against the
warehouse — which is what makes `genql graph rebuild` possible.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class SemanticCatalogReader(Protocol):
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]: ...

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]: ...

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]: ...

    def read_column_profiles(self, ref: SchemaRef) -> Sequence[ColumnProfile]: ...
