"""A fake satisfying the protocol proves services can be tested without a database."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.ports.catalog_reader import CatalogReader


class FakeCatalogReader:
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, schema: str) -> Sequence[Column]:
        return []

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return []


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeCatalogReader(), CatalogReader)
