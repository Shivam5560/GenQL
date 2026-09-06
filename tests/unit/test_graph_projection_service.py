"""Reads objects and constraints back from the semantic store, writes them
into the graph. Same shape as CatalogScanService: read via one port, write
via another, return a typed report."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.graph.graph_projection_service import GraphProjectionService

OBJECTS = [
    DatabaseObject(
        datasource_name="local",
        schema_name="shop",
        object_name="customer",
        object_type=ObjectType.TABLE,
    )
]
CONSTRAINTS = [
    Constraint(
        datasource_name="local",
        schema_name="shop",
        object_name="order",
        constraint_name="order_customer_fkey",
        constraint_type=ConstraintType.FOREIGN_KEY,
        definition="FOREIGN KEY (customer_id) REFERENCES customer(id)",
        referenced_object_name="customer",
    )
]


class FakeReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return OBJECTS

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return CONSTRAINTS


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[DatabaseObject] = []
        self.constraints: list[Constraint] = []

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        self.objects.extend(objects)
        return len(objects)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        self.constraints.extend(constraints)
        return len(constraints)


def test_project_writes_everything_it_reads() -> None:
    writer = FakeWriter()
    ref = SchemaRef(datasource_name="local", schema_name="shop")

    report = GraphProjectionService(FakeReader(), writer).project(ref)

    assert report.objects == 1
    assert report.edges == 1
    assert report.total == 2
    assert writer.objects == OBJECTS
    assert writer.constraints == CONSTRAINTS
