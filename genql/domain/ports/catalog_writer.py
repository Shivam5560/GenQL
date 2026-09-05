"""Persists structural metadata into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class CatalogWriter(Protocol):
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int: ...

    def write_columns(self, columns: Sequence[Column]) -> int: ...

    def write_constraints(self, constraints: Sequence[Constraint]) -> int: ...
