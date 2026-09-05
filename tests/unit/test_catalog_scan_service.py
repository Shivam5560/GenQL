"""Services are tested with fakes. No database, no network, no container."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.services.discovery.catalog_scan_service import CatalogScanService

OBJECT = DatabaseObject(
    schema_name="shop", object_name="customer", object_type=ObjectType.TABLE, row_estimate=7
)
COLUMN = Column(
    schema_name="shop",
    object_name="customer",
    column_name="c_state",
    ordinal=2,
    data_type="text",
    is_nullable=True,
)
CONSTRAINT = Constraint(
    schema_name="shop",
    object_name="customer",
    constraint_name="customer_pkey",
    constraint_type=ConstraintType.PRIMARY_KEY,
    definition="PRIMARY KEY (c_customer_sk)",
)


class FakeReader:
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return [OBJECT]

    def read_columns(self, schema: str) -> Sequence[Column]:
        return [COLUMN]

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return [CONSTRAINT]


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[DatabaseObject] = []
        self.columns: list[Column] = []
        self.constraints: list[Constraint] = []

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        self.objects.extend(objects)
        return len(objects)

    def write_columns(self, columns: Sequence[Column]) -> int:
        self.columns.extend(columns)
        return len(columns)

    def write_constraints(self, constraints: Sequence[Constraint]) -> int:
        self.constraints.extend(constraints)
        return len(constraints)


def test_scan_persists_everything_it_reads() -> None:
    writer = FakeWriter()
    report = CatalogScanService(FakeReader(), writer).scan("shop")

    assert report.objects == 1
    assert report.columns == 1
    assert report.constraints == 1
    assert writer.objects == [OBJECT]
    assert writer.columns == [COLUMN]
    assert writer.constraints == [CONSTRAINT]


def test_total_counts_all_records() -> None:
    report = CatalogScanService(FakeReader(), FakeWriter()).scan("shop")
    assert report.total == 3
