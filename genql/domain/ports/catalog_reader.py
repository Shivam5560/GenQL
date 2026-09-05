"""Reads structural metadata from the target warehouse."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class CatalogReader(Protocol):
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]: ...

    def read_columns(self, schema: str) -> Sequence[Column]: ...

    def read_constraints(self, schema: str) -> Sequence[Constraint]: ...
