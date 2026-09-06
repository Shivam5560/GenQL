"""Persists one schema's objects and FK edges into the graph projection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class GraphWriter(Protocol):
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int: ...

    def write_edges(self, constraints: Sequence[Constraint]) -> int: ...
