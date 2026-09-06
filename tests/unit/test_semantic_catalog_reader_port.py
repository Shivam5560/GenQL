"""A fake satisfying the protocol proves the projection service is testable
without Postgres."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef


class FakeSemanticCatalogReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return []

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeSemanticCatalogReader(), SemanticCatalogReader)
