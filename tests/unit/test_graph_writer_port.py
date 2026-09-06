from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.ports.graph_writer import GraphWriter


class FakeGraphWriter:
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        return len(objects)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        return len(constraints)


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeGraphWriter(), GraphWriter)
